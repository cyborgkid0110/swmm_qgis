.. table:: Data and Data Structure for Hydraulic Modeling
   :widths: 20 32 23 25
   :class: longtable

   +------------------------+------------------------------------------+------------------------------------------+------------------------------------------------+
   | Data Group             | Specific Data                            | Format/Structure                         | Notes/Explanation                              |
   +========================+==========================================+==========================================+================================================+
   | **1. Topography & Spatial Data** | High-resolution Digital Elevation Model (DEM/LiDAR) (minimum 5m, ideally 1m). | Raster (GeoTIFF, .asc)                   | Determines surface flow direction and flood-prone areas. |
   |                        | Topographic maps (contours, elevation points). | Vector (Shapefile, .dwg, .dxf)           | Supplements DEM, especially in urban areas.    |
   |                        | Land use / Land cover maps.              | Vector/Raster (Shapefile)                | Determines roughness coefficient (Manning's n) and infiltration capacity. |
   +------------------------+------------------------------------------+------------------------------------------+------------------------------------------------+
   | **2. River, Lake, and Canal Network** | River, canal, and ditch network (centerlines, cross-sections, bed elevation, bank elevation). | Vector (Shapefile, .dwg) with attributes | Fundamental data for open channel flow.        |
   |                        | Lakes, detention ponds, reservoirs (bed elevation, normal water level, storage capacity). | Vector with attributes                   | Important for urban drainage regulation and flood storage. |
   +------------------------+------------------------------------------+------------------------------------------+------------------------------------------------+
   | **3. Urban Drainage System** | Sewer network layout (location, length, diameter, slope, upstream/downstream invert elevations, flow direction). | Line vector (Shapefile, .dwg) in GIS     | Must be checked and corrected to ensure connectivity and hydraulic consistency. |
   |                        | Manholes and flow split chambers (location, elevation, dimensions). | Point vector (Shapefile) with attributes | Connection points between surface water and underground system. |
   |                        | Pumping stations (location, capacity, operation rules). | Point vector (Shapefile) with attributes | Controls drainage flow within the sewer network. |
   |                        | Outlets and outfalls (location, elevation, discharge capacity). | Point vector (Shapefile) with attributes | Discharge points from the drainage system to receiving water bodies. |
   |                        | Dams, culverts, and hydraulic structures (dimensions, crest elevation, operation rules). | Vector with detailed attributes          | Controls flow and water levels on rivers and canals. |
   +------------------------+------------------------------------------+------------------------------------------+------------------------------------------------+
   | **4. Hydrology, Meteorology & Boundaries** | Rainfall time series (minute/hourly from automatic rain gauges). | Time-series tables (.csv, .xlsx)         | Main input for rainfall-induced flooding models. |
   |                        | Water levels and discharge at river boundaries (hourly/daily). | Tables (.csv, .xlsx)                     | Defines upstream and downstream boundary conditions. |
   |                        | Evaporation, temperature, humidity (for large-scale hydrological modeling). | Tables (.csv, .xlsx)                     | Used in rainfall-runoff models at basin scale. |
   +------------------------+------------------------------------------+------------------------------------------+------------------------------------------------+
   | **5. Pollution Sources (If Water Quality Modeling)** | Locations and discharge of pollution sources (industrial zones, craft villages, residential areas). | Point vector (.shp) with data tables     | Important when extending hydraulic models to water quality simulation. |
   |                        | Pollutant concentrations in wastewater (COD, BOD, TSS, N, P...). | Tables (.csv, .xlsx)                     | Inputs for water quality models.               |
   +------------------------+------------------------------------------+------------------------------------------+------------------------------------------------+

.. note:: The quality of a hydraulic model heavily depends on the quality of input data.
