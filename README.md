Export Parcels Toolbox Technical Reference Manual

1. Tool Overview and Purpose

The ExportParcels tool serves as the high-throughput data acquisition engine for obtaining parcel data for land use analysis and modeling. Its primary function is the automated extraction of Ohio parcel data from the GeoOhio ArcGIS Online Parcel Service into a localized, high-performance environment. As the canonical first step in the pipeline, it ensures data integrity by populating the raw_inputs feature dataset with standardized records, providing a consistent baseline for all subsequent spatial analytics and downstream modeling.

2. Technical Specifications and Requirements

System architects must ensure the following environment configurations and service endpoints are established for tool operation:

* Source Service URL: https://services2.arcgis.com/MlJ0G8iWUyC7jAmu/arcgis/rest/services/OhioStatewidePacels_full_view/FeatureServer/0 (Note: The "Pacels" orthography is intentional to maintain alignment with the registered REST service name).
* Service Coordinate System: WGS84 (EPSG 4326).
* Target Coordinate System: NAD 1983 NBS 2011 StatePlane Ohio South FIPS 3402 (WKID 3735).
* Connectivity: Requires an authenticated, active ArcGIS Pro portal connection to the GeoOhio organization.
* Architecture: Python Toolbox (.pyt) utilizing arcpy and concurrent.futures for multi-threaded I/O operations.

3. Operational Modes

The tool supports two distinct execution profiles. Production Mode is designed for pipeline automation and state-wide consistency, while Test Mode provides a sandboxed environment for schema validation and connectivity audits.

Feature	Production Mode	Test Mode
Default State	Active by default.	Explicitly toggled via "Test Mode" parameter.
Output Path	raw_inputs/Parcels_Raw	raw_inputs/Parcels_Test_{Scope}_{RunID}*
Idempotency/Cache	Skips download if Parcels_Raw exists (unless "Force Redownload" is flagged).	Ignores existing cache; executes atomic download without affecting production data.
Pipeline Integration	Canonical source for all downstream analytical tools.	Isolated for manual inspection; ignored by automated pipeline triggers.

*Note: In the Test Mode naming convention, {Scope} is dynamically replaced by the specific County name or District number selected during parameterization.

4. Geographic Scope and Data Organization

The tool implements spatial filtering through the COUNTY attribute, where values are strictly stored as uppercase strings.

District Resolution Logic

When a user selects a District scope, the tool programmatically resolves the selection into individual county-level tasks using the internal DISTRICT_MAP dictionary. This ensures that a single high-level selection translates into multiple parallel worker threads for the constituent counties.

County Inventory (88 Counties)

			
ADAMS	FAIRFIELD	LAWRENCE	PICKAWAY
ALLEN	FAYETTE	LICKING	PIKE
ASHLAND	FRANKLIN	LOGAN	PORTAGE
ASHTABULA	FULTON	LORAIN	PREBLE
ATHENS	GALLIA	LUCAS	PUTNAM
AUGLAIZE	GEAUGA	MADISON	RICHLAND
BELMONT	GREENE	MAHONING	ROSS
BROWN	GUERNSEY	MARION	SANDUSKY
BUTLER	HAMILTON	MEDINA	SCIOTO
CARROLL	HANCOCK	MEIGS	SENECA
CHAMPAIGN	HARDIN	MERCER	SHELBY
CLARK	HARRISON	MIAMI	STARK
CLERMONT	HENRY	MONROE	SUMMIT
CLINTON	HIGHLAND	MONTGOMERY	TRUMBULL
COLUMBIANA	HOCKING	MORGAN	TUSCARAWAS
COSHOCTON	HOLMES	MORROW	UNION
CRAWFORD	HURON	MUSKINGUM	VAN WERT
CUYAHOGA	JACKSON	NOBLE	VINTON
DARKE	JEFFERSON	OTTAWA	WARREN
DEFIANCE	KNOX	PAULDING	WASHINGTON
DELAWARE	LAKE	PERRY	WAYNE
ERIE			WILLIAMS
			WOOD
			WYANDOT

5. Execution Logic and Resilience

To handle the scale of state-wide parcel datasets, the tool utilizes an advanced concurrency and checkpointing architecture:

1. Parallel Execution & Thread Safety: The tool implements concurrent.futures to manage worker threads for per-county downloads. To ensure thread safety and prevent data corruption during parallel cursor operations, the tool utilizes internal threading.Lock mechanisms (_write_lock and _read_lock). Furthermore, each thread creates a unique, in-memory Feature Layer (identified by thread ID) to maintain namespace isolation.
2. State Persistence (Checkpointing): Resiliency is managed via a parcel_export_progress.json file. This checkpoint is stored within the specific RunID sub-directory, ensuring that progress tracking is unique to each execution instance. This allows the tool to resume interrupted runs by identifying previously committed counties.
3. Run Identification: Every execution instance is assigned a unique RunID (Format: LI_YYYYMMDD_HHMMSS), which governs the naming of logs, checkpoint folders, and test-mode outputs.

6. Output Dataset Specifications

All outputs are localized to the project geodatabase within the raw_inputs feature dataset.

* Dataset Initialization: If the raw_inputs dataset is absent, the tool automatically initializes it, explicitly defining the spatial reference as WKID 3735.
* Production Geometry: The final output is written to the Parcels_Raw feature class, projected and standardized for the LandInventory workflow.

7. Logging and Monitoring

Architectural transparency is maintained through a structured logging system:

* Log Hierarchy: Each execution generates a dedicated directory named after the RunID. Within this directory, a comprehensive log file titled ExportParcels_Log_{RunID}.txt is created.
* Thread Monitoring: The log records atomic updates from each county worker thread, providing precise timestamps and success/failure status messages. This facilitates rapid debugging of network timeouts or service interruptions at the individual county level.

8. Pipeline Governance

The ExportParcels tool is the foundational implementation of the LandInventory Pipeline governance philosophy. By enforcing strict data standards, coordinate system consistency, and thread-safe acquisition logic, it protects the integrity of the entire analytical stack, ensuring that all subsequent tools operate on validated, authoritative data.
