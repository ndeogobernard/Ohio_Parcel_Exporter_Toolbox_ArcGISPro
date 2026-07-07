# Export Parcels Toolbox

The Export Parcels toolbox is a standalone Python toolbox (`.pyt`) designed for development and testing. Its primary purpose is to download Ohio parcel data from the GeoOhio ArcGIS Online Parcel Service into a local project geodatabase.

## Overview
The Export Parcels toolbox handles the data acquisition phase of the LandInventory Pipeline. It downloads statewide parcel data from the GeoOhio Feature Service and manages cached data to prevent redundant downloads, offering distinct modes for production and testing.

* **Methodology:** The tool queries the GeoOhio parcel service, which stores data in WGS84 (EPSG 4326), and writes the output locally into a `raw_inputs` feature dataset using the target CRS (WKID: 3735). It uses a threading lock mechanism to safely download data from individual counties in parallel.
* **Important Notes:**
  * The `COUNTY` field in the source service stores uppercase county names (e.g., `COUNTY = 'LAKE'`).
  * The service URL contains an intentional typo (`OhioStatewidePacels_full_view`) which matches the registered service name on GeoOhio.
* **More Information:** The service URL is `https://services2.arcgis.com/MlJ0G8iWUyC7jAmu/arcgis/rest/services/OhioStatewidePacels_full_view/FeatureServer/0`.

## Requirements
* **Software:** Designed for ArcGIS Pro.
* **Settings/Configurations:** Requires an active ArcGIS Pro portal connection to GeoOhio.

## Installation
To use this tool, add the `ExportParcels.pyt` file to your ArcGIS Pro project's Toolboxes folder, or connect to the folder containing the `.pyt` file in the Catalog pane.

## Usage

### Operating Modes
The tool operates in two distinct modes depending on how you want to handle the outputs:

1. **Production Mode (Default):** The tool automatically writes the data to `raw_inputs/Parcels_Raw`. This acts as the canonical input read by all downstream LandInventory Pipeline tools. A cache check is applied by default; if `Parcels_Raw` already exists, the tool skips the download to save time unless a forced redownload is requested.
2. **Test Mode:** Activated by the "Test Mode" checkbox. The output writes to `raw_inputs/Parcels_Test_{Scope}_{RunID}` and never touches the production data. The cache check is completely skipped. Downstream pipeline tools do not read test outputs automatically. This is ideal for validating portal connections, inspecting schemas, or running manual tests before committing to a full statewide production run.

### Tool Parameters

| Parameter | Description | Data Type |
| :--- | :--- | :--- |
| **Target Geodatabase** | The project geodatabase where the `raw_inputs` feature dataset will be created. | Workspace/Geodatabase |
| **Test Mode** | Checkbox to run the tool in test mode, appending `{Scope}_{RunID}` to the output name and bypassing the cache check. | Boolean |
| **Force Redownload** | Checkbox to force the tool to download data in Production mode even if a cached `Parcels_Raw` file already exists. | Boolean |
| **Scope / County** | The specific geographic scope to download, selectable from a list of Ohio counties or predefined Districts (District 1 through District 12). | String |

## Outputs
All spatial outputs are saved within a feature dataset named `raw_inputs`.

* **`Parcels_Raw`:** The primary feature class containing downloaded parcels (generated only in Production mode).
* **`Parcels_Test_{Scope}_{RunID}`:** The test feature class generated when "Test Mode" is checked.
* **`ExportParcels_Log_{run_id}.txt`:** A text file containing the log messages and execution timestamps for the run.
* **`parcel_export_progress.json`:** A checkpoint JSON file tracking which counties have been successfully downloaded.
