# Autonomous GIS Workbench - Project Brief

## 1. Product Vision

Autonomous GIS Workbench is a standalone geospatial automation platform that turns natural-language user requests into reliable GIS workflows. The product is not intended to replace QGIS, ArcGIS, Netcad, or AutoCAD, and it should not be implemented as a plugin inside those ecosystems.

The goal is to operate as an independent GIS automation workbench: users upload or connect geospatial data, describe a multi-step task in natural language, and receive validated map outputs, transformed datasets, quality-control reports, and reproducible process logs. If needed, users can later edit the outputs in QGIS, ArcGIS, Netcad, or CAD tools.

The core differentiation is not a single GIS operation such as buffer, clip, or CRS conversion. Existing GIS software already performs those operations well. The differentiation is autonomous execution of long, repetitive, error-prone workflows with geodetic correctness, topology checks, cost control, and auditability.

## 2. Strategic Positioning

The product should be positioned as:

> A standalone, natural-language GIS automation and quality-control workbench for preparing, validating, transforming, analyzing, and packaging spatial data.

It should focus on process acceleration rather than map editing. Manual cartographic editing, CAD-style drawing, and advanced desktop GIS interface features should remain outside the product scope.

The platform should support open and common output formats so it can coexist with established professional tools:

- GeoPackage
- Shapefile
- GeoJSON
- KML
- DXF
- CSV
- PDF reports
- JSON process logs

## 3. Target Users

Primary early users:

- GIS and surveying offices
- Geomatics engineers
- Small technical teams handling repeated spatial data preparation
- Municipal or infrastructure teams that need repeatable GIS outputs but cannot increase staff capacity

Future enterprise users:

- Water utilities
- Municipal GIS departments
- Infrastructure operators
- Real-estate, logistics, and field-operation companies with recurring spatial analysis needs

## 4. Core Problem

GIS professionals can already perform individual operations quickly in QGIS or ArcGIS. The real pain appears when workflows become long, repetitive, cross-format, and quality-sensitive.

Examples:

- A folder contains dozens of shapefiles, DXF files, and CSV coordinate tables.
- Some layers have missing or wrong CRS definitions.
- Some geometries are invalid, duplicated, overlapping, or not closed.
- Data must be transformed into a target CRS such as TUREF TM30 / EPSG:5254.
- A standard analysis must be repeated over many files.
- Outputs must be delivered as a consistent package with data, map preview, report, and processing log.

The product should reduce the time and error risk of these workflows.

## 5. Product Principle

Use a small number of agents and a strong deterministic workflow/tool registry.

Avoid building a system where every step requires an LLM call. LLMs should be used as orchestrators and interpreters, not as the executor for every GIS operation.

Recommended execution model:

```text
Natural language request
-> lightweight intent parser / planner
-> deterministic workflow registry
-> validated GIS tools
-> CRS and topology guard
-> result package and report
-> LLM fallback only when necessary
```

The preferred product architecture is:

- Few agents
- Many tested tools
- Reusable workflow templates
- Deterministic execution
- LLM fallback for ambiguous or custom tasks

## 6. Cost Strategy

The product must be cheaper than assigning a human operator to repetitive GIS work.

Token cost should stay low by following these rules:

- Use one LLM call to understand the task and select a workflow.
- Use deterministic Python/PostGIS/GDAL/GeoPandas tools for execution.
- Reuse cached workflow plans.
- Do not call the LLM per file, per layer, or per geometry.
- Use local or smaller models for classification and workflow selection.
- Use stronger models only for complex planning, report generation, or ambiguous requests.

The target model is:

```text
One plan -> many deterministic operations
```

not:

```text
One LLM call -> one small GIS operation
```

## 7. Technical Foundation

Recommended stack:

- Python 3.12+
- Maplibre for mapping
- FastAPI for API and streaming responses
- Pydantic v2 for strict input/output validation
- LangGraph only where graph-based orchestration is necessary
- GeoPandas, Shapely 2.x, pyproj, GDAL/Fiona/Rasterio where appropriate
- PostGIS and pgRouting for database-backed workflows
- pgvector only for workflow/RAG search when needed
- LiteLLM for model abstraction
- Docker for reproducible runtime

Important architectural rule:

LLM output must never be executed directly without validation. Generated code, when needed, must run only in a sandboxed environment with strict resource and filesystem limits.

## 8. Core Architecture

Recommended modules:

```text
src/ageo/
  domain/
    value_objects/
    services/
    ports/
  application/
    workflows/
    tools/
    orchestration/
    agents/
    schemas/
  infrastructure/
    gis/
    rag/
    sandbox/
    persistence/
  interface/
    api/
    web/
```

### Domain Layer

Pure Python, no framework imports.

Responsibilities:

- CRS rules
- topology rules
- geometry specifications
- tool contracts
- workflow plan entities

### Application Layer

Coordinates user requests and workflows.

Responsibilities:

- deterministic workflow registry
- tool registry
- lightweight planner
- optional LangGraph orchestration
- validation and retry policies

### Infrastructure Layer

External adapters.

Responsibilities:

- GeoPandas execution
- PostGIS execution
- OSM/Overpass data access
- vector store / RAG
- sandbox execution
- persistence

### Interface Layer

User-facing API and web UI.

Responsibilities:

- FastAPI endpoints
- streaming progress events
- map visualization
- upload/download flows
- result package delivery

## 9. Workflow Registry First

The first version should implement a deterministic workflow registry before investing heavily in multi-agent behavior.

Example workflow records:

```text
road_fetch_and_buffer
preflight_quality_check
crs_normalization
format_conversion_package
topology_report
batch_layer_overlay
csv_to_point_layer
dxf_to_geopackage
delivery_package_builder
```

Each workflow should define:

- name
- supported natural-language patterns
- required parameters
- optional parameters
- input data requirements
- deterministic tool chain
- expected output format
- validation rules
- failure modes

## 10. Example MVP Scenario

Initial scenario:

> Fetch all roads in Kutahya and apply a buffer only to selected streets.

The minimal workflow:

```text
User request
-> parse location: Kutahya
-> detect road-fetch intent
-> fetch administrative boundary from OSM
-> fetch highway=* geometries inside boundary
-> show all roads on map
-> if street names are supplied, filter OSM road name field
-> transform selected roads to metric CRS
-> apply buffer distance in meters
-> transform result back to display CRS
-> return GeoJSON with layer markers
```

Important CRS rule:

Do not buffer in EPSG:4326. Transform to a suitable metric CRS first. For Kutahya and western Turkey examples, TUREF / TM30 EPSG:5254 can be used as an initial default, but the long-term system should choose the CRS by location.

Example natural-language commands:

```text
Kutahya'daki tum yollari haritaya cek
```

```text
Kutahya'daki "Ataturk Caddesi" icin 25 m buffer uygula
```

## 11. MVP Feature Set

The first professional MVP should include:

1. Natural-language task box
2. Map preview
3. File upload
4. Deterministic workflow registry
5. Tool registry
6. CRS validation
7. Topology validation
8. OSM data fetch for simple demos
9. Batch-friendly execution model
10. Result export as GeoJSON or GeoPackage
11. Process trace panel
12. Error explanations in user language

Do not prioritize:

- full CAD editing
- QGIS/ArcGIS plugin integration
- complex UI for manual digitizing
- free-form generated code as the main path

## 12. Tool Registry

Initial deterministic tools:

- load_vector
- save_vector
- fetch_osm_boundary
- fetch_osm_features
- reproject
- buffer_metric
- clip
- intersect
- difference
- dissolve
- spatial_join
- validate_geometry
- repair_geometry
- detect_crs
- calculate_area
- calculate_length
- package_outputs

Each tool must have:

- typed input schema
- typed output schema
- CRS requirements
- geometry type requirements
- deterministic implementation
- unit tests

## 13. Agents

Keep the agent system small.

Recommended early agents:

- Planner: converts natural language into workflow/tool calls.
- Critic/Validator: checks whether selected workflow and parameters are safe and semantically aligned.
- Reporter: summarizes results and warnings.

Avoid many always-on agents. More agents means more token cost, more latency, and more failure points.

## 14. RAG Strategy

RAG should support the workflow registry, not replace it.

Useful RAG content:

- GIS operation recipes
- CRS rules
- Turkish geodetic references
- common workflow patterns
- known tool pitfalls
- example validated workflows

RAG should be lazy-loaded. The application must not fail at startup because an embedding model or vector database is unavailable. If vector search is unavailable, the system should fall back to bundled JSON recipes or deterministic workflows.

## 15. Safety and Reliability

Strict rules:

- Never run unvalidated LLM output.
- Prefer deterministic tools over generated code.
- If generated code is necessary, run it only in sandbox.
- Never expose raw sensitive data to LLMs.
- Use pyproj for CRS transformations.
- Do not perform manual CRS string manipulation.
- Use Pydantic v2 strict schemas.
- Record process logs for every operation.

## 16. User Experience

The UI should feel like an operational workbench, not a marketing website.

Primary screen:

- left panel: query, workflow trace, warnings, outputs
- right panel: map preview
- output drawer: generated files and reports

The system should show:

- what it understood
- which workflow it selected
- which CRS it used
- which layers were processed
- which warnings were found
- where the output files are

## 17. Product Roadmap

### Phase 1 - Deterministic Core

- Build tool registry
- Build workflow registry
- Implement road fetch and selected-street buffer
- Implement CRS-safe buffer
- Implement trace events
- Implement map output

### Phase 2 - Data Preparation Workbench

- Upload shapefile, GeoPackage, GeoJSON, CSV
- Detect CRS and geometry type
- Validate topology
- Export corrected or flagged outputs
- Produce QA report

### Phase 3 - Batch Automation

- Folder-based processing
- Repeat same workflow over many files
- Delivery package generation
- Standard naming and metadata manifest

### Phase 4 - Smarter Planner

- Natural-language planner chooses workflows
- RAG-assisted workflow grounding
- Human-in-the-loop questions for ambiguous CRS or parameters
- Workflow memory and caching

### Phase 5 - Enterprise Adaptors

- PostGIS
- ArcGIS REST services
- WMS/WFS
- internal utility or municipal data sources
- role-based access and audit logs

## 18. Success Criteria

The MVP is successful if a user can:

- write a natural-language spatial task
- watch the system select a deterministic workflow
- receive a map output
- see CRS and topology decisions
- export a usable result
- understand every major processing step

The product is commercially promising if it reduces a 1-3 hour repetitive GIS preparation workflow into a 5-15 minute supervised process.

## 19. What Not To Build

Do not build:

- a QGIS clone
- an ArcGIS clone
- a Netcad clone
- an AutoCAD-like editor
- a plugin-first product
- a system where LLM writes and executes arbitrary GIS code for every request

The product should be a standalone automation workbench that produces outputs professionals can continue editing elsewhere.

## 20. One-Sentence Summary

Autonomous GIS Workbench is a standalone, natural-language geospatial automation platform that uses a small number of agents and a strong deterministic workflow/tool registry to execute long GIS processes safely, cheaply, and with geodetic correctness.
