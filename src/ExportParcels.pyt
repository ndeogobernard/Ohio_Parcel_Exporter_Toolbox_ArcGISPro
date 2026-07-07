# =============================================================================
# Tool: ExportParcels
# Group 1 — Data Acquisition
# Standalone .pyt for development and testing
#
# Purpose:
#   Downloads Ohio parcel data from the GeoOhio ArcGIS Online Parcel Service
#   into the project geodatabase raw_inputs dataset.
#
# Output naming:
#   Production mode (default):
#     Output always writes to raw_inputs/Parcels_Raw.
#     This is the canonical input read by all downstream tools.
#     Cache check applies — skips download if Parcels_Raw exists
#     unless Force Redownload is checked.
#
#   Test mode ("Test Mode" checkbox checked):
#     Output writes to raw_inputs/Parcels_Test_{Scope}_{RunID}.
#     Never touches Parcels_Raw. Cache check is skipped.
#     Downstream pipeline tools do NOT read test outputs automatically.
#     Use test mode to validate the portal connection, inspect schemas,
#     or run individual tools manually against a small dataset before
#     committing to a full statewide production run.
#
# Service:
#   https://services2.arcgis.com/MlJ0G8iWUyC7jAmu/arcgis/rest/services/
#   OhioStatewidePacels_full_view/FeatureServer/0
#   ("Pacels" typo is intentional — matches registered service name.)
#   Service CRS: WGS84 (EPSG 4326).
#   COUNTY field stores uppercase county names (e.g. COUNTY = 'LAKE').
#
# Requires:
#   Active ArcGIS Pro portal connection to GeoOhio.
# =============================================================================

import arcpy
import os
import json
import datetime
import concurrent.futures
import threading


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PARCEL_SERVICE_URL = (
    "https://services2.arcgis.com/MlJ0G8iWUyC7jAmu/arcgis/rest/services/"
    "OhioStatewidePacels_full_view/FeatureServer/0"
)

PRODUCTION_FC    = "Parcels_Raw"
OUTPUT_DATASET   = "raw_inputs"
OUTPUT_CRS_WKID  = 3735
TARGET_CRS       = arcpy.SpatialReference(OUTPUT_CRS_WKID)

# COUNTY field values in the service are uppercase
OHIO_COUNTIES = [
    "ADAMS","ALLEN","ASHLAND","ASHTABULA","ATHENS","AUGLAIZE","BELMONT","BROWN",
    "BUTLER","CARROLL","CHAMPAIGN","CLARK","CLERMONT","CLINTON","COLUMBIANA",
    "COSHOCTON","CRAWFORD","CUYAHOGA","DARKE","DEFIANCE","DELAWARE","ERIE",
    "FAIRFIELD","FAYETTE","FRANKLIN","FULTON","GALLIA","GEAUGA","GREENE",
    "GUERNSEY","HAMILTON","HANCOCK","HARDIN","HARRISON","HENRY","HIGHLAND",
    "HOCKING","HOLMES","HURON","JACKSON","JEFFERSON","KNOX","LAKE","LAWRENCE",
    "LICKING","LOGAN","LORAIN","LUCAS","MADISON","MAHONING","MARION","MEDINA",
    "MEIGS","MERCER","MIAMI","MONROE","MONTGOMERY","MORGAN","MORROW","MUSKINGUM",
    "NOBLE","OTTAWA","PAULDING","PERRY","PICKAWAY","PIKE","PORTAGE","PREBLE",
    "PUTNAM","RICHLAND","ROSS","SANDUSKY","SCIOTO","SENECA","SHELBY","STARK",
    "SUMMIT","TRUMBULL","TUSCARAWAS","UNION","VAN WERT","VINTON","WARREN",
    "WASHINGTON","WAYNE","WILLIAMS","WOOD","WYANDOT"
]

DISTRICT_MAP = {
    "District 1":  ["ALLEN","DEFIANCE","HANCOCK","HARDIN","PAULDING",
                    "PUTNAM","VAN WERT","WYANDOT"],
    "District 2":  ["FULTON","HENRY","LUCAS","OTTAWA","SANDUSKY",
                    "SENECA","WILLIAMS","WOOD"],
    "District 3":  ["ASHLAND","CRAWFORD","ERIE","HURON","LORAIN",
                    "MEDINA","RICHLAND","WAYNE"],
    "District 4":  ["ASHTABULA","MAHONING","PORTAGE","STARK","SUMMIT","TRUMBULL"],
    "District 5":  ["COSHOCTON","FAIRFIELD","GUERNSEY","KNOX",
                    "LICKING","MUSKINGUM","PERRY"],
    "District 6":  ["DELAWARE","FAYETTE","FRANKLIN","MADISON",
                    "MARION","MORROW","PICKAWAY","UNION"],
    "District 7":  ["AUGLAIZE","CHAMPAIGN","CLARK","DARKE","LOGAN",
                    "MERCER","MIAMI","MONTGOMERY","SHELBY"],
    "District 8":  ["BUTLER","CLERMONT","CLINTON","GREENE",
                    "HAMILTON","PREBLE","WARREN"],
    "District 9":  ["ADAMS","BROWN","HIGHLAND","JACKSON","LAWRENCE",
                    "PIKE","ROSS","SCIOTO"],
    "District 10": ["ATHENS","GALLIA","HOCKING","MEIGS","MONROE",
                    "MORGAN","NOBLE","VINTON","WASHINGTON"],
    "District 11": ["BELMONT","CARROLL","COLUMBIANA","HARRISON",
                    "HOLMES","JEFFERSON","TUSCARAWAS"],
    "District 12": ["CUYAHOGA","GEAUGA","LAKE"],
}

_write_lock = threading.Lock()
_read_lock  = threading.Lock()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def generate_run_id():
    return datetime.datetime.now().strftime("LI_%Y%m%d_%H%M%S")


def setup_log(log_folder, run_id):
    d = os.path.join(log_folder, run_id)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"ExportParcels_Log_{run_id}.txt")


def write_log(log_path, message, also_print=True):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if also_print:
        arcpy.AddMessage(message)


def setup_checkpoint(checkpoint_folder, run_id):
    d = os.path.join(checkpoint_folder, run_id)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "parcel_export_progress.json")


def load_checkpoint(cp_path):
    if os.path.exists(cp_path):
        with open(cp_path) as f:
            return set(json.load(f).get("completed_counties", []))
    return set()


def save_checkpoint(cp_path, completed):
    with open(cp_path, "w") as f:
        json.dump({
            "completed_counties": list(completed),
            "updated": datetime.datetime.now().isoformat()
        }, f, indent=2)


def build_output_name(scope, single_county, test_mode, run_id):
    """
    Determine the output feature class name.
    Production: always Parcels_Raw.
    Test:       Parcels_Test_{scope_label}_{RunID}
    """
    if not test_mode:
        return PRODUCTION_FC

    if scope == "Statewide (all 88 counties)":
        scope_label = "Statewide"
    elif scope == "Single County" and single_county:
        scope_label = single_county.title().replace(" ", "_")
    elif "ODOT" in scope:
        scope_label = scope.replace("ODOT ", "Dist").replace(" ", "")
    else:
        scope_label = "Custom"

    return f"Parcels_Test_{scope_label}_{run_id}"


def get_output_path(gdb_path, fc_name):
    return os.path.join(gdb_path, OUTPUT_DATASET, fc_name)


def ensure_raw_inputs_dataset(gdb_path, log_path):
    ds = os.path.join(gdb_path, OUTPUT_DATASET)
    if not arcpy.Exists(ds):
        arcpy.management.CreateFeatureDataset(gdb_path, OUTPUT_DATASET, TARGET_CRS)
        write_log(log_path, f"  Created feature dataset: {OUTPUT_DATASET}")


def check_production_cache(gdb_path, log_path):
    """Check whether Parcels_Raw already exists. Only applies in production mode."""
    out_path = get_output_path(gdb_path, PRODUCTION_FC)
    if arcpy.Exists(out_path):
        count = int(arcpy.management.GetCount(out_path)[0])
        write_log(log_path,
            f"  Cache found: Parcels_Raw exists ({count:,} records).")
        return True, count
    return False, 0


def download_county_worker(county, gdb_path, out_fc_name,
                           cp_path, completed, log_path):
    """
    Download one county from the service.
    Each call creates its own feature layer — safe for parallel execution.
    Returns (county, success, count, message).
    """
    county_safe = county.replace(" ", "_")
    lyr_name    = f"parcel_lyr_{county_safe}_{threading.get_ident()}"
    sql         = f"COUNTY = '{county}'"

    try:
        arcpy.management.MakeFeatureLayer(
            PARCEL_SERVICE_URL, lyr_name, sql
        )

        n = int(arcpy.management.GetCount(lyr_name)[0])
        if n == 0:
            arcpy.management.Delete(lyr_name)
            return county, True, 0, "No records returned"

        out_path = get_output_path(gdb_path, out_fc_name)
        ds_path  = os.path.join(gdb_path, OUTPUT_DATASET)

        with _write_lock:
            if arcpy.Exists(out_path):
                arcpy.management.Append(lyr_name, out_path, "NO_TEST")
            else:
                arcpy.conversion.FeatureClassToFeatureClass(
                    lyr_name, ds_path, out_fc_name
                )

        arcpy.management.Delete(lyr_name)

        with _read_lock:
            completed.add(county)
            save_checkpoint(cp_path, completed)

        return county, True, n, f"Downloaded {n:,} records"

    except Exception as e:
        try:
            arcpy.management.Delete(lyr_name)
        except Exception:
            pass
        return county, False, 0, f"ERROR: {str(e)}"


# ---------------------------------------------------------------------------
# Toolbox
# ---------------------------------------------------------------------------
class Toolbox:
    def __init__(self):
        self.label   = "Export Parcels"
        self.alias   = "ExportParcels"
        self.tools   = [ExportParcels]


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
class ExportParcels:

    def __init__(self):
        self.label       = "Export Parcels"
        self.description = (
            "Downloads Ohio parcel data from the GeoOhio ArcGIS Online "
            "Parcel Service. Production mode writes to Parcels_Raw "
            "(the canonical pipeline input). Test mode writes to a "
            "separate named output and never touches Parcels_Raw."
        )
        self.canRunInBackground = False

    # ------------------------------------------------------------------
    def getParameterInfo(self):

        p0 = arcpy.Parameter(
            displayName="Project Geodatabase",
            name="project_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input"
        )
        p0.filter.list = ["Local Database"]

        p1 = arcpy.Parameter(
            displayName="Log Folder",
            name="log_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )

        p2 = arcpy.Parameter(
            displayName="Checkpoint Folder",
            name="checkpoint_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )

        p3 = arcpy.Parameter(
            displayName="Scope",
            name="scope",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )
        p3.filter.type = "ValueList"
        p3.filter.list = (
            ["Statewide (all 88 counties)"]
            + [f"ODOT {d}" for d in DISTRICT_MAP]
            + ["Single County"]
        )
        p3.value = "Statewide (all 88 counties)"

        p4 = arcpy.Parameter(
            displayName="County Name (Single County scope only)",
            name="single_county",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        p4.filter.type = "ValueList"
        p4.filter.list = sorted(OHIO_COUNTIES)
        p4.enabled     = False

        p5 = arcpy.Parameter(
            displayName="Test Mode (write to named output, do not overwrite Parcels_Raw)",
            name="test_mode",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        p5.value = False
        p5.description = (
            "When checked: output writes to Parcels_Test_{Scope}_{RunID} "
            "and never touches Parcels_Raw. Use for portal connection tests, "
            "schema inspection, or running individual tools against a small "
            "county dataset before committing to a full statewide run. "
            "Downstream pipeline tools do NOT read test outputs automatically.\n\n"
            "When unchecked (production): output always writes to Parcels_Raw. "
            "Cache check applies."
        )

        p6 = arcpy.Parameter(
            displayName="Force Redownload (production mode only — ignore cache)",
            name="force_redownload",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        p6.value = False
        p6.description = (
            "Only applies in production mode (Test Mode unchecked). "
            "If checked, deletes existing Parcels_Raw and downloads fresh. "
            "Has no effect in test mode — test outputs are always new."
        )

        p7 = arcpy.Parameter(
            displayName="Parallel Workers",
            name="parallel_workers",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input"
        )
        p7.value = 4
        p7.description = (
            "Simultaneous county download threads for multi-county runs. "
            "4 is the tested default. Each thread creates its own feature "
            "layer. GDB writes are serialised regardless of this setting."
        )

        return [p0, p1, p2, p3, p4, p5, p6, p7]

    # ------------------------------------------------------------------
    def isLicensed(self):
        return True

    # ------------------------------------------------------------------
    def updateParameters(self, parameters):
        scope     = parameters[3].valueAsText or ""
        test_mode = bool(parameters[4].value)

        # Show county picker only for Single County scope
        parameters[4].enabled = (scope == "Single County")
        if scope != "Single County":
            parameters[4].value = None

        # Force redownload only relevant in production mode
        parameters[6].enabled = not test_mode

        return

    # ------------------------------------------------------------------
    def updateMessages(self, parameters):
        if (parameters[3].valueAsText == "Single County"
                and not parameters[4].value):
            parameters[4].setErrorMessage(
                "Select a county name when Scope = Single County."
            )
        return

    # ------------------------------------------------------------------
    def execute(self, parameters, messages):

        gdb_path          = str(parameters[0].value)
        log_folder        = str(parameters[1].value)
        checkpoint_folder = str(parameters[2].value)
        scope             = str(parameters[3].value)
        single_county     = parameters[4].valueAsText or ""
        test_mode         = bool(parameters[5].value) if parameters[5].value else False
        force_redownload  = bool(parameters[6].value) if parameters[6].value else False
        parallel_workers  = int(parameters[7].value) if parameters[7].value else 4

        run_id    = generate_run_id()
        log_path  = setup_log(log_folder, run_id)
        cp_path   = setup_checkpoint(checkpoint_folder, run_id)
        out_name  = build_output_name(scope, single_county, test_mode, run_id)

        write_log(log_path, "=" * 60)
        write_log(log_path, "ExportParcels")
        write_log(log_path, f"Run ID           : {run_id}")
        write_log(log_path, f"Mode             : {'TEST' if test_mode else 'PRODUCTION'}")
        write_log(log_path, f"Scope            : {scope}")
        write_log(log_path, f"Output FC        : {out_name}")
        write_log(log_path, f"Force redownload : {force_redownload}")
        write_log(log_path, f"Parallel workers : {parallel_workers}")
        write_log(log_path, f"Service URL      : {PARCEL_SERVICE_URL}")
        write_log(log_path, f"Output CRS       : WKID {OUTPUT_CRS_WKID}")
        write_log(log_path, "=" * 60)

        if test_mode:
            write_log(log_path,
                "TEST MODE: Output will NOT overwrite Parcels_Raw. "
                f"Writing to: {out_name}")
            arcpy.AddWarning(
                f"TEST MODE active. Writing to '{out_name}'. "
                "Pipeline tools will not read this output automatically.")

        # ── Production cache check (skipped in test mode) ──────────
        if not test_mode:
            cache_exists, cached_count = check_production_cache(
                gdb_path, log_path)
            if cache_exists and not force_redownload:
                write_log(log_path,
                    f"Parcels_Raw exists ({cached_count:,} records). "
                    "Skipping. Check Force Redownload to refresh.")
                arcpy.AddMessage(
                    f"Cache found: Parcels_Raw ({cached_count:,} records). "
                    "Download skipped.")
                return
            if cache_exists and force_redownload:
                arcpy.management.Delete(
                    get_output_path(gdb_path, PRODUCTION_FC))
                write_log(log_path,
                    "Deleted existing Parcels_Raw (Force Redownload).")

        # ── Build county list ──────────────────────────────────────
        if scope == "Statewide (all 88 counties)":
            county_list = OHIO_COUNTIES[:]
        elif scope == "Single County":
            county_list = [single_county.upper()]
        elif "ODOT" in scope:
            dist_key    = scope.replace("ODOT ", "")
            county_list = DISTRICT_MAP.get(dist_key, [])
        else:
            county_list = OHIO_COUNTIES[:]

        write_log(log_path, f"Counties to download: {len(county_list)}")

        # ── Checkpoint resume (production only) ────────────────────
        if test_mode:
            completed = set()
            pending   = county_list[:]
        else:
            completed = load_checkpoint(cp_path)
            if completed:
                write_log(log_path,
                    f"Resuming: {len(completed)} counties already done.")
            pending = [c for c in county_list if c not in completed]

        write_log(log_path, f"Counties pending   : {len(pending)}")

        # ── Ensure dataset exists ──────────────────────────────────
        ensure_raw_inputs_dataset(gdb_path, log_path)

        # ── Download ───────────────────────────────────────────────
        error_counties = []

        arcpy.SetProgressor(
            "step", "Downloading parcels...", 0, len(pending), 1)

        if len(pending) <= 1 or parallel_workers == 1:
            for county in pending:
                _, success, count, msg = download_county_worker(
                    county, gdb_path, out_name,
                    cp_path, completed, log_path
                )
                if success:
                    write_log(log_path, f"  {county:<15} {msg}")
                else:
                    error_counties.append(county)
                    write_log(log_path, f"  {county:<15} FAILED — {msg}")
                    arcpy.AddWarning(f"County failed: {county} — {msg}")
                arcpy.SetProgressorPosition()
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=parallel_workers
            ) as executor:
                futures = {
                    executor.submit(
                        download_county_worker,
                        county, gdb_path, out_name,
                        cp_path, completed, log_path
                    ): county
                    for county in pending
                }
                for future in concurrent.futures.as_completed(futures):
                    county, success, count, msg = future.result()
                    if success:
                        write_log(log_path, f"  {county:<15} {msg}")
                    else:
                        error_counties.append(county)
                        write_log(log_path,
                            f"  {county:<15} FAILED — {msg}")
                        arcpy.AddWarning(f"County failed: {county}")
                    arcpy.SetProgressorPosition()

        arcpy.ResetProgressor()

        # ── Project to pipeline CRS if needed ─────────────────────
        out_path = get_output_path(gdb_path, out_name)
        if arcpy.Exists(out_path):
            sr = arcpy.Describe(out_path).spatialReference
            if sr.factoryCode != OUTPUT_CRS_WKID:
                write_log(log_path,
                    f"Reprojecting WKID {sr.factoryCode} -> {OUTPUT_CRS_WKID}...")
                proj = out_path + "_proj"
                arcpy.management.Project(out_path, proj, TARGET_CRS)
                arcpy.management.Delete(out_path)
                arcpy.management.Rename(proj, out_name)
                write_log(log_path, "Reprojection complete.")
            else:
                write_log(log_path, f"CRS confirmed: WKID {OUTPUT_CRS_WKID}.")

        final_count = (
            int(arcpy.management.GetCount(out_path)[0])
            if arcpy.Exists(out_path) else 0
        )

        # ── Summary ────────────────────────────────────────────────
        write_log(log_path, "\n" + "=" * 60)
        write_log(log_path, "SUMMARY")
        write_log(log_path,
            f"  Mode                : {'TEST' if test_mode else 'PRODUCTION'}")
        write_log(log_path, f"  Output FC           : {out_name}")
        write_log(log_path, f"  Counties requested  : {len(county_list)}")
        write_log(log_path, f"  Counties completed  : {len(completed)}")
        write_log(log_path, f"  Counties failed     : {len(error_counties)}")
        if error_counties:
            write_log(log_path, f"  Failed: {', '.join(error_counties)}")
        write_log(log_path, f"  Total records       : {final_count:,}")
        write_log(log_path, f"  Output path         : {out_path}")
        write_log(log_path, f"  Run ID              : {run_id}")
        write_log(log_path, "=" * 60)

        if test_mode:
            write_log(log_path,
                "  TEST OUTPUT — pipeline tools will not read this "
                "automatically. To use in pipeline, copy or rename to "
                "Parcels_Raw.")

        if error_counties:
            arcpy.AddWarning(
                f"{len(error_counties)} failure(s). "
                f"Run ID {run_id} — rerun to resume.")
        else:
            arcpy.AddMessage(
                f"ExportParcels complete. {final_count:,} records in "
                f"'{out_name}'. Run ID: {run_id}")
        return

    # ------------------------------------------------------------------
    def postExecute(self, parameters):
        return
