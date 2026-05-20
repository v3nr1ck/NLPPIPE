# CMMS Work Order API Payload — Deep Research Report

**Scope:** Top 15–20 CMMS / EAM platforms in 2025–2026, with the typical fields each one transmits through its API (or exposes via its work-order data model where the API mirrors the form). This is a buyer-/integrator-facing reference, not vendor marketing.

**Method:** Each profile is drawn from the vendor's own developer documentation (Swagger / REST guides / SDKs / object references) where available, falling back to UI/help-center field references and third-party integration platforms (Pipedream, Make, Makini, Supergood, Ibexa Connect, Workato) for vendors whose docs are gated. Field names below use each platform's own attribute names so they can be matched 1:1 to the actual request/response body.

**A note on terminology before the profiles:** vendors split "work orders" into different real objects — Maximo and SAP call it a *Work Order* / *Maintenance Order*, Limble calls every executable record a *Task*, ServiceChannel calls it a *WO* with a *ContractInfo* envelope, Corrigo issues *WoCreateCommand*, and Brightly stores both a `WorkOrderId` (system) and `WorkOrderNumber` (user-facing). The "trade or craft" the user asked about is also named differently in every system — `WORKTYPE` / `worktype` (Maximo), `Trade` (ServiceChannel), `Work Category` (Brightly), `Trade` (Infor EAM activity), `Craft` (legacy), `Category` (MaintainX/UpKeep). I call these out per platform and then reconcile them in the synthesis section at the end.

---

## 1. IBM Maximo (Maximo Application Suite — `MXAPIWO` / `MXAPIWODETAIL`)

**API:** REST/JSON over OSLC. Modern endpoint is `/oslc/os/mxapiwo` (legacy `/maxrest/rest/mbo/workorder` and `/maxrest/rest/os/MXWO` still exist but Steven Shull at IBM recommends the JSON API).

**Object structure:** `MXAPIWO` (header) and `MXAPIWODETAIL` (header + tasks + plans + reservations + safety). Key attributes are `SiteID` + `WoNum`. The work-order schema is one of the largest in the industry — 200+ persistent attributes — but the high-frequency payload fields are:

| Field | Description |
|---|---|
| `WONUM` | Work order number (auto-keyed if blank) |
| `WORKORDERID` | Internal numeric ID |
| `DESCRIPTION` | Short description |
| `DESCRIPTION_LONGDESCRIPTION` | Long description |
| `STATUS` | WAPPR, APPR, INPRG, WMATL, WSCH, COMP, CLOSE, CAN |
| `STATUSDATE` | Timestamp of last status change |
| `WORKTYPE` | EM (Emergency), CM (Corrective), PM (Preventive), CP (Capital), etc. — this is Maximo's "craft/work-class" field at the WO level |
| `WOPRIORITY` | Numeric priority (1–5 typically) |
| `ASSETNUM` | Asset being worked on |
| `LOCATION` | Location code |
| `SITEID` | Site code (required) |
| `ORGID` | Organization |
| `PARENT` | Parent WO (for follow-ups and hierarchies) |
| `JPNUM` | Job Plan number |
| `PMNUM` | PM record that generated this WO |
| `LEAD` | Lead craft (person/labor) |
| `SUPERVISOR` | Supervisor |
| `OWNER` / `OWNERGROUP` | Assigned person / persongroup |
| `CREWID` | Crew |
| `CREWWORKGROUP` | Crew work group |
| `REPORTEDBY` | Reporter |
| `REPORTDATE` | Report date |
| `TARGSTARTDATE` / `TARGCOMPDATE` | Target start / completion |
| `SCHEDSTART` / `SCHEDFINISH` | Scheduled start / finish |
| `ACTSTART` / `ACTFINISH` | Actual start / finish |
| `ESTDUR` | Estimated duration (hours) |
| `ESTLABHRS` / `ESTLABCOST` | Estimated labor hours / cost |
| `ESTMATCOST` / `ESTTOOLCOST` / `ESTSERVCOST` | Estimated material / tool / service cost |
| `ACTLABHRS` / `ACTLABCOST` | Actual labor hours / cost |
| `ACTMATCOST` / `ACTTOOLCOST` / `ACTSERVCOST` | Actual material / tool / service cost |
| `FAILURECODE` / `PROBLEMCODE` / `CAUSECODE` / `REMEDYCODE` | Failure-class taxonomy |
| `GLACCOUNT` | GL account |
| `CHARGESTORE` | Charge to inventory store flag |
| `ISTASK` / `TASKID` / `PARENT` | Task vs. WO header |
| `WPLABOR` / `WPMATERIAL` / `WPTOOL` / `WPSERVICE` | Child collections (work plan) |
| `LABTRANS` / `MATUSETRANS` / `TOOLTRANS` | Actual labor / material / tool transactions |
| `WOSERVICEADDRESS` | Service address |
| `CONTRACTNUM` | Contract |
| `CLASSSTRUCTUREID` | Classification |

The `mxapiwodetail` object structure exposes child objects (`invreserve`, `woactivity`, `wplabor`, `wpmaterial`, `wptool`, `assignment`, `woservicea`, `wosafetyplan`) via dot notation in `oslc.select`. Schemas can be retrieved live at `/oslc/jsonschemas/mxapiwodetail`.

**Trade/craft note:** Maximo separates "work class" (`WORKTYPE` — EM/CM/PM/CP) from "craft" (the skill on the labor record). Trade-level fields live on `WPLABOR.CRAFT` / `LABTRANS.CRAFT`, not on the WO header.

---

## 2. SAP Plant Maintenance — S/4HANA `API_MAINTENANCEORDER` (V2 OData) and `OP_API_MAINTENANCEORDER_0001` (V4 successor)

**API:** OData v2 / v4 published on SAP Business Accelerator Hub. The entity is `A_MaintenanceOrder` with composition associations to `_MaintenanceOrderOperation`, `_MaintenanceOrderComponent`, `_LongText`, and `_StatusDescriptiveAttribute`.

**Per the published JSON schema (SAP help portal), the typical maintenance order payload is:**

| Field | Description |
|---|---|
| `MaintenanceOrder` / `orderId` | SAP order number (32 char internal ID + visible order number) |
| `externalID` | External ID for IDoc / 3rd-party correlation (max 40) |
| `MaintenanceOrderType` / `type` | 1: Breakdown, 2: Inspections, 3: Installation, 4: Planned, 5: Disposal, 6: Operations |
| `equipmentID` / `MaintenanceOrderEquipment` | SAP equipment master number (32 char internal) |
| `functionalLocationID` / `FunctionalLocation` | Functional location |
| `MaintPriority` / `priority` | 5: Low, 10: Medium, 15: High, 20: Very High, 25: Critical (Customizing-driven) |
| `MaintPriorityDesc` | Description text |
| `status` | NEW, PBD (Published), CPT (Completed), CSD (Closed) |
| `MaintOrdProcessPhaseCode` | 01–09 lifecycle phases (09 = Completion / closed-out) |
| `SystemStatus` / `UserStatus` | SAP system + user status strings (CRTD, REL, TECO, CLSD…) |
| `basicStartDate` / `basicEndDate` | Basic scheduling dates |
| `actualStartDate` / `actualEndDate` | Actuals |
| `personResponsible` / `MaintenancePersonResponsible` | Assigned planner |
| `plant` / `MaintenancePlanningPlant` | Plant code |
| `workCenter` / `MainWorkCenter` | Main work center (this is SAP's craft/trade equivalent) |
| `plannedDuration` / `plannedDurationUnit` | Duration + unit |
| `actualDuration` / `actualDurationUnit` | Duration + unit |
| `MaintenanceActivityType` | Activity type code (PM01, PM02, etc.) |
| `MaintenanceNotification` | Linked notification number |
| `description.shortDescription` | Header description (40 char) |
| `description.longDescription` | Long text (via `_LongText` association) |
| `MaintenanceObjectIsDown` | Asset-down flag |
| `MalfunctionStartDateTime` / `MalfunctionEndDateTime` | Outage window |
| `adminData.createdBy` / `createdOn` / `changedBy` / `changedOn` | Audit |
| `_MaintenanceOrderOperation` (child) | Operations, each with own `OperationWorkCenter`, planned/actual work hours, control key |
| `_MaintenanceOrderComponent` (child) | Material reservations |
| `SettlementRule` | Cost settlement |

**Trade/craft note:** SAP doesn't use the word "trade" — the trade equivalent at the order level is `MainWorkCenter`, and at the operation level `OperationWorkCenter`. The V4 successor adds boolean status fields (`MaintenanceOrderHasError`, `_IsInProcess`, `_IsReleased`) and consistent SAP_Messages messaging per entity.

---

## 3. Oracle eAM (E-Business Suite / Fusion Cloud Maintenance)

**API:** EBS Integrated SOA Gateway / Fusion REST `maintenanceWorkOrders`.

Per Oracle's eAM Work Management guide, the typical eAM work order header transmits:

- **Identifiers:** `WorkOrderNumber`, `OrganizationCode`
- **Asset linkage:** `AssetNumber`, `AssetGroup`, `AssetActivity` (the standard activity that pre-loads BOM/route/quality plan), `MaintenanceObjectId`
- **Classification:** `WorkOrderType` (Routine, Preventive, Emergency, Facilities, Rebuild — drives reporting/budgeting), `WorkOrderSubType`, `Class`, `Status`
- **Ownership:** `Department` (defaults from Asset — Oracle's analog to a craft/work center), `Owner`, `Planner`, `Supervisor`, `RequestedBy`
- **Priority:** `Priority` (High / Medium / Low; customisable)
- **Scheduling:** `ScheduledStartDate`, `ScheduledCompletionDate`, `ActualStartDate`, `ActualCompletionDate`, `FirmPlannedFlag`, `ShutdownType`
- **Cost & accounting:** `Project`, `Task`, `MaterialAccount`, `MaterialOverheadAccount`, `OverheadAccount`, `ResourceAccount`, `ResourceOverheadAccount`, `OutsideProcessingAccount`
- **Description & failure:** `Description`, `WorkRequestNumber`, `FailureEntryRequired`, `FailureCode`, `CauseCode`, `ResolutionCode`
- **Children:** operations (each with department, resources, materials), material requirements, resource requirements, quality plans

**Trade/craft note:** Oracle's craft equivalents are the `Department` on the header and the `Resource` on each operation; technicians have `ResourceInstances` and skill endorsements.

---

## 4. Infor EAM (now HxGN EAM)

**API:** REST/JSON on top of the legacy SOAP "Web Services Facade." The endpoint pattern is `/workorders/{id}` where `id` follows the Infor convention `entitycode#organizationcode` (e.g. `WO-12345#MAINT`). Defined in OpenAPI 3 inside each tenant's Swagger.

Per the Infor EAM "Defining regular work order headers" doc + the developer guide, the WO header transmits:

- **Identity / org:** `workOrderNumber`, `organization`, `class`
- **Description:** `description` (and rich-text long description via the `commentText` child)
- **Asset / location:** `equipment` (single or Multiple Equipment flag), `location`, `routeOfEquipment` (linear-asset support — start/end points for linear assets like pipelines/roads, with `fromPoint`, `toPoint`, geographical reference, direction)
- **Type & priority:** `workOrderType`, `priority`, `criticality`, `costCode`, `productionPriority`
- **Status / ownership:** `status`, `assignedTo`, `assignedBy`, `personResponsible`, `department`, `crew`
- **Failure model:** `problemCode`, `failureCode`, `actionTaken`, `causeCode`, `route`, `inspectionStatus`
- **Scheduling:** `scheduledStartDate`, `scheduledEndDate`, `targetDate`, `actualStartDate`, `actualEndDate`
- **Downtime & meter:** `downtimeCost`, `downtimeHours`, `lastMeterReading`
- **Project & cost:** `project`, `budget`, `customer`, `property`, `building`, `floor/unit`
- **Children:** activities (each with `tradeCode`, `taskPlan`, `materialList`, `startDate`, `endDate`, `estimatedHours`, `peopleRequired`), `laborBookings` (POSTed separately at `/workorders/laborbookings/{number}`), parts, comments, custom fields, user-defined fields (`UDF1`…`UDFn`).

**Trade/craft note:** Infor uses `tradeCode` on the activity, not the header. The header's "department" is an org bucket; the trade attaches to each activity line.

---

## 5. Fiix (Rockwell Automation)

**API:** Custom JSON-RPC-style HTTP API (not RESTful — every call is a POST with a `className` discriminator). Documented at `fiixlabs.github.io/api-documentation`. SDKs in Java + JavaScript. The work-order object is `WorkOrder` (v5) or the newer `WorkOrderV6` (these don't share API access — a tenant on v6 cannot read v5 work orders via API).

The fields commonly transmitted (mapped from the configurable Work Request form and the v5 SDK setters) are:

- `id`, `code` (work-order number — string, sortable but configurable so date-created / id are also exposed)
- `description` (long text)
- `priority` (lookup-table — Highest / High / Medium / Low / Lowest by default, but each tenant can rewrite)
- `status` (lookup-table; grouped into Requested, Active, Inactive, Complete categories)
- `maintenanceType` (Reactive, Preventive, Inspection, etc.)
- `assetID` (single asset; multi-asset variants supported on the form)
- `locationID` / `siteID` (required on every request)
- `assignedUserID`, `assignedTeamID`, `assignedVendorID`, additional-workers collection
- `projectID`, `budgetID`, `glAccountID`
- `customTagIDs[]`, `failureCodeIDs[]` (pre-set in tenant settings)
- `startDate`, `dueDate` (suggested completion), `completedDate`
- `estimatedHours`, `estimatedCost`
- `tasks[]` (child collection — each task has its own description, assigned user, completion state, push-notification flag)
- `parts[]` (with quantity used)
- `attachments[]` (images, docs)
- Custom fields (Enterprise tier only) — added to the form via Settings → CMMS Settings → Lookup Tables

Webhooks fire on `task` events with `taskID`, `status`, `category`, `user` (see Limble for a similar webhook shape — Fiix is conceptually similar).

**Trade/craft note:** Fiix uses `maintenanceType` rather than craft; the closest "trade" concept is the lookup-table that defines technician skills, attached to the user object, not the WO.

---

## 6. eMaint X5 (Fluke Reliability)

**API:** REST/JSON, configurable per tenant. eMaint's WO object is one of the most form-driven in this list — virtually every field on the WO is admin-configurable, so the "typical payload" is the default form plus any custom fields the customer added.

Default header fields:

- `workOrderNumber` (sequential, prefixable)
- `requesterName` / `requesterEmail` / `requesterPhone`
- `assetID` / `assetDescription` / `assetType` / `assetSubType` / `site` / `location` / `building` / `lineNumber`
- `assetPriority` (asset-level criticality) and WO-level `priority`
- `problemDescription` (long text)
- `instructions` (the task list — most commonly used for PM)
- `parts[]` and `materials[]` (with quantity)
- `requiredSkills[]` / `craft` / `trade` (configurable)
- `estimatedLaborHours` / `actualLaborHours`
- `requestedDate`, `dueDate`, `scheduledDate`, `completedDate`
- `status` (configurable workflow — typically Open / In Progress / On Hold / Closed / Cancelled)
- `attachments[]` (photos, docs, meter readings via Fluke instruments)
- Linked PM / route / inspection ID
- `signatures[]` (sanitation, quality, safety sign-offs)
- Approval routing fields

Custom fields are first-class — eMaint is regularly extended for ISO/OSHA compliance with audit-trail fields, calibration certificate fields, and Fluke Connect sensor stream fields.

**Trade/craft note:** eMaint's craft field is fully customisable; out-of-the-box it appears as `Skill` or `Trade` on the work assignment, not strictly required on the header.

---

## 7. Brightly Asset Essentials (Siemens / formerly Dude Solutions)

**API:** REST/JSON. Endpoints include `/workOrders`, `/workOrders/{id}`. UTC dates throughout (API account should be set to UTC). Pagination by `PageNumber` + `PageSize`. Custom fields are filtered by `WorkCategory` — they only appear on a WO when the WO's category matches the field's category restriction.

Two key identifier columns:
- `WorkOrderId` — the system back-end numeric ID, used in all GET / PUT
- `WorkOrderNumber` — the user-facing label, freely editable (useful for ERP / external-system parity)

Standard header fields (mapped from the new WO form and the API docs):

| Field | Description |
|---|---|
| `WoStatus` | Required. Pulls from configured WO status list |
| `Title` | Required |
| `WorkOrderNumber` | Auto if blank |
| `Priority` | Required |
| `Originator` | Auto-populated to current user |
| `WorkRequested` | Detailed description |
| `Address` | Where the work happens (separate from source location) |
| `SourceType` | One of Asset / Location / Site / Meter Title / Unknown |
| `Assets[]` / `Locations[]` / `Sites[]` | Set based on SourceType (only one source type per WO; multiple sources of that type allowed) |
| `WorkType` | "Why" — Corrective, Storm Damage, Inspection, etc. |
| `WorkCategory` | The trade/craft — HVAC, Plumbing, Electrical, IT, etc. (this is Brightly's official "trade" field) |
| `Problem` / `Cause` | Failure model — `Problem` is linked hierarchically to `WorkCategory` |
| `Expected` | Expected completion date |
| `Created` / `Assigned` dates | Manually editable |
| `AssignedTo` (users + crews) | Routing-rule driven |
| `CostCenter` | Pulls from source's cost center first; falls back to template |
| `Project` | Optional project link |
| `EstimatedCost` / `ActualCost` |
| `Tasks[]` | Selected from Tasks Library or created inline (only shown after WO is saved) |
| `LaborEntries[]` | Added inline once WO is saved (technician, hours, rate) |
| `PurchasedParts[]` / `InventoryParts[]` | Each with quantity, location, unit cost |
| `EquipmentUsage[]` | Meter readings tied to the WO |
| `Attachments[]` | Photos + docs |
| `RequiredDocuments[]` | When the WO inherits required-doc slots from a schedule |
| Custom fields (filtered by WorkCategory) |

**Trade/craft note:** This is the field the user explicitly asked about — Brightly's `WorkCategory` was renamed from "WO Type" specifically to align with industry "trade" semantics, and a separate `WorkType` was added on top of it to capture "why" the work is being performed.

---

## 8. ServiceChannel

**API:** REST/JSON, also OData. Two creation flows: **Classic** (caller sets everything) and **IssueList** (caller selects from a hierarchical issue tree, which auto-populates Trade / Category / Provider). `POST /v3/workorders`. Webhooks fire on every status transition with the full work-order object.

The typical ServiceChannel WO payload:

```json
{
  "ContractInfo": {
    "SubscriberId": 2014917243,
    "LocationId": 2006071467,    // OR StoreId — StoreId requires SubscriberId
    "StoreId": "100",
    "TradeName": "HVAC",         // this is the trade/craft
    "ProviderId": 2000090505,
    "ProviderRank": 0,
    "ApprovalCode": ""
  },
  "Category": "REPAIR",          // also: CAPEX, MAINTENANCE, PARTS ORDER, INSPECTION, RECALL…
  "Priority": "P2 - 8 Hours",    // also P1 EMERGENCY, P3 24 HOURS, P4 72 HOURS, P5 WEEK, etc.
  "Nte": 1000,                   // not-to-exceed dollar amount
  "CallDate": "2017-08-23T19:35:00Z", // ALWAYS UTC
  "Description": "ELEVATOR/ESCALATOR / Elevator / Freight Elevator / Freight Elevator Inspection",
  "ProblemCode": "Freight Elevator Inspection",
  "IssueRequestInfo": {           // IssueList approach only
    "AreaId": 4935,
    "ExtendedAreaName": "ELEVATOR/ESCALATOR",
    "ProblemType": "Elevator",
    "AssetType": "Freight Elevator"
  },
  "AssetId": 1339628,            // if asset-based; LocationId becomes optional
  "AdditionalFields": [          // troubleshooting Q&A as name/value pairs
    { "Header": "Client Phone Number", "Description": "+1 555 123 4567" }
  ],
  "Attachments": [
    { "Name": "test attachment", "Description": "for test only",
      "Path": "201706/d8f0792e-81ef-4fcb-95df-1ae0c1be9cd9-test.txt" }
  ],
  "Providers": [                  // multi-vendor dispatch
    { "Rank": 1, "Nte": 400, "FullName": "LF INCORPORATED LLC", "Id": 2000090505 }
  ]
}
```

Response (and webhook payload) additionally includes:

- `Id`, `Number`, `PurchaseNumber`
- `Status.Primary` (OPEN, IN PROGRESS, COMPLETED, CANCELLED) + `Status.Extended` (CONFIRMED, etc.)
- `Caller`, `CreatedBy`, `UpdatedBy`
- `ScheduledDate`, `ScheduledDate_DTO` (with TZ offset), `CompletedDate`, `UpdatedDate`, `ExpirationDate`
- `CurrencyAlphabeticalCode`
- `Source` (the channel that created it — dashboard, IVR, API, etc.)
- `Notes[]` (each with `Id`, `Number`, `NoteData`)
- `LinkedWorOrderIds[]` (for follow-up / recall handling)

**Trade/craft note:** `ContractInfo.TradeName` is the explicit trade and is required. The trade dictates which provider pool the WO routes to.

---

## 9. Corrigo (JLL CorrigoPro Enterprise / CorrigoPro Direct)

**API:** REST/JSON on Corrigo Enterprise (new), SOAP/XML on legacy. CorrigoPro Direct adds a *partner-facing* REST API for service providers to receive and act on customer WOs. WO creation goes through `v1/cmd/WoCreateCommand`.

Per the published data models, the WO entity contains:

- `Id`, `Number` (e.g. `15475000343`), `PurchaseNumber`
- `TypeCategory` (Request, Work Order, Inspection)
- `Asset` (with `Id`, `Name`, `ModelId`, `TypeId`, `ParentId`, `RootId`)
- `Location` (with `ModelId`, `Address`, `TimeZone`)
- `WorkOrderCost` (with `CostsTotal`, `PaymentAmount`, `VendorInvoiceTotal`, `GlAccount`, `JobCode`, `AuthorizationCode`, `BillingRule`, `CheckNumber`, `IsPreBilled` flag)
- `Status` (with `ApStateId`, `ApStatusId` for AP-state tracking)
- `CurrencyTypeId`
- `WoNumberPrefix`, `WoNumberDigits`
- `Entity` (the subscriber's brand — KFC, Walmart, etc.)
- `SchedulingWindow`, `AdvanceNotice`, `RoundApptTimeTo`
- `WorkPlanAutoCancel`, `WorkPlanChildResolution`, `WorkPlanAutoDependency`
- `AutoAssignEnabled`, `BackupRouting`
- `ComputeSchedule`, `ComputeAssignments` flags (set during create)
- `CustomFields[]` (per-property — also exposed via `PropertyCustomField`)
- `Documents[]` and `RequiredDocuments[]` (typed slots — Fire Sprinkler Inspection, Elevator Certificate, Photographic Proof, etc., each with `DocumentId`, `DocumentDate`, `Description`, `Status` — Reviewed/Submitted, `Attachment`)
- `CheckList[]` (technician punch list — each item with `Description`, completion state, technician comment)
- `Contact` (requester — name, phone, type Customer/Provider)
- `Technician` (assigned tech)
- `CompletionDetails` (with GPS check-in/check-out coordinates, completion comments, repair category)
- `LanguageId`, `TimeZone`

**Trade/craft note:** Corrigo handles trade via the `TaskCategory` on the linked Task / standard work-order template, plus the `RepairCategory` returned at completion. Customers can require providers to pick from their location-specific category/code list at check-out.

---

## 10. MaintainX

**API:** REST/JSON at `api.getmaintainx.com/v1/workorders`. Cursor pagination (`cursor=` query param + `nextCursor` response field).

Per MaintainX's own work-order form reference and the Ibexa/Make integration descriptions, the create payload typically contains:

| Field | Description |
|---|---|
| `title` | Required — "What needs to be done?" — ≤ 255 chars |
| `description` | ≤ 4096 chars |
| `priority` | (configurable; defaults: None / Low / Medium / High) |
| `workType` | Preventive, Reactive, or Other |
| `locationId` | Single location |
| `assetId` | Single asset (disappears from the form if sub-WOs are added) |
| `assetStatus` | Update asset status inline (e.g. set to Offline when WO is opened) |
| `assignees[]` | Users **and/or** Teams (multi-assignee supported) |
| `estimatedTime` | Hours + minutes |
| `startDate` / `startTime` | Defaults to 12:00 AM on start date |
| `dueDate` / `dueTime` | Defaults to 12:00 PM on due date |
| `recurrence` | Object — none, daily, weekly, monthly, custom |
| `procedureId` / `procedureFields[]` | Procedures (checklists) attached to the WO; each step can be Pass/Fail/Flag |
| `categories[]` | Built-in (Safety, SOP) + custom — this is closest to the "trade" field |
| `vendors[]` | Multi-vendor |
| `parts[]` | Each with `partId`, `amountUsed`, optional `unitCost` override, `location` (for multi-location parts) |
| `files[]` / `pictures[]` | Attachments |
| `subWorkOrders[]` | Parent/child WO structure — when present, `assetId` moves to each sub-WO |
| `externalUrl` / `shareWithExternalEmail` | Premium/Enterprise — externally shareable work orders |
| Custom fields | Site-admin defined; can be marked required |

**Trade/craft note:** MaintainX uses `Categories` (plural — multi-select) as the trade equivalent. There is no dedicated craft field on the WO; the procedure attached to the WO carries the skill context.

---

## 11. UpKeep

**API:** REST/JSON at `api.onupkeep.com/api/v2`. Session-token auth (Enterprise-plan gated). Versioned via `upkeep-version` header. Detailed reference at `developers.onupkeep.com`.

The `POST /work-orders` payload (confirmed by the Pipedream connector code, which mirrors the doc):

| Field | Type | Description |
|---|---|---|
| `title` | String, required | |
| `description` | String | |
| `priority` | Integer | |
| `category` | String | One of the account's configured categories (or default ones — UpKeep's trade equivalent) |
| `dueDate` | ISO 8601 | e.g. `2022-09-07T13:26:53` |
| `asset` (`assetId`) | String | UpKeep asset ID |
| `location` (`locationId`) | String | UpKeep location ID |
| `assignedToUser` (`userId`) | String | Primary assignee |
| `additionalUsers[]` | String[] | Additional workers |
| `assignedToTeam` | String | Team |
| `parts[]` | objects with `partId` + `respectivePartQuantity` | |
| `partThresholdType` | "manual" / "auto" | If `manual`, inventory is NOT decremented when a part is added |
| `time` | Integer | Total time spent (minutes) |
| `cost` | Integer | Additional cost assigned to the WO |
| `status` | "open" / "complete" / "onHold" / "inProgress" | |
| `image` / `files[]` | File IDs |
| `recurrence` | (legacy PM via `/preventive-maintenance`) | |
| `customFields[]` | One per work-order custom field defined under `/custom-fields/workorders` |

The response object also returns `id`, `createdAt`, `updatedAt`, `createdByUser`, `requestedByUser`, computed `status`, and (if expanded via `?includes=`) the full asset / location / user objects.

UpKeep's work-order custom field types: `singleLineText`, `multiLineText`, `number`, `currency`, `date`, `dropdown` — each posted as a `fieldValue` object with the matching `…Value` property.

**Trade/craft note:** UpKeep uses `category` as the trade. Asset-side `category` and WO-side `category` are different fields on different objects.

---

## 12. Limble CMMS

**API:** REST/JSON at `api.limblecmms.com/v2/` (regional variants: `ca-`, `eu-`, `au-`, `21cfr-`). Basic auth (Base64 ClientID:ClientSecret). Pagination via `limit/page` (preferred, going forward) or `orderBy/cursor` (legacy, being deprecated).

**Important terminology:** in Limble, a "Task" is the unified record for work orders, PMs, work requests, inspections, and audit tasks. The `/tasks` endpoint is the work-order endpoint.

Task fields commonly transmitted:

- `taskID` (numeric — internal)
- `name` / `taskName` (the title)
- `taskDescription` (long text)
- `taskType` (`wo`, `pm`, `wr`, `inspection`, `audit`)
- `priorityID` (default 1: High, 2: Medium, 3: Low — but tenants can extend in Settings → General Task Settings → Priorities)
- `assetID` / `locationID`
- `assignedToUser` (a single user login, typically email) / `assignedToTeam` / `assignedToMultiUsers[]`
- `createdOn` / `dueOn` / `dateCompleted` / `due`
- `status` (configurable per-tenant)
- `customTags[]`
- `instructions[]` (each with `instructionID`, `label`, `description`, optional parent-child responses for branching, sort order, response value)
- `parts[]` (with quantity used)
- `tools[]`
- `customFields[]` (up to 3 on work-request forms; unlimited on tasks)
- `timeLogged[]` (each entry with user, start/end, billable flag, GL)
- `bills[]` / `costsTotal` (Enterprise)
- `assetFields[]` — Limble can surface fields from the linked asset right onto the task

Webhooks fire on task events with `taskID`, `status` (CREATED, DELETED, CHANGED DUE DATE, CHANGED ASSIGNMENT, COMPLETE, CHANGED COMPLETED TASK, COMPLETED TASK REOPENED, CHANGED TASK NAME, CHANGED TASK DESCRIPTION, ADDED COMMENT TO TASK, CUSTOM TAG ADDED TO TASK, CUSTOM TAG REMOVED FROM TASK, LOGGED TIME ON TASK), `category` ("task"), and `user`.

**Trade/craft note:** Limble's craft field is delivered via `customTags` (drag-and-drop multi-tag) rather than a built-in trade attribute. Larger tenants typically configure a "Trade" custom tag or a single-select custom field for it.

---

## 13. Hippo CMMS (now Eptura Asset)

**API:** REST/JSON at `api.hippocmms.com` (gated; key issued by Hippo/Eptura support). Hippo's product is in a renaming transition into Eptura Asset, and the publicly-reachable Hippo API is documented privately, but the field shape is consistent across the Hippo, Eptura Asset, and ManagerPlus (also Eptura) work-order objects:

- `workOrderNumber`
- `title` / `summary`
- `description`
- `requesterID` (or guest requester via the request portal)
- `priority` (Critical / High / Medium / Low / None)
- `status` (Open / In Progress / On Hold / Completed / Cancelled — configurable)
- `assetID` / `equipmentID` (with multi-asset support)
- `locationID` / `facilityID` / `building` / `floor` / `siteID`
- `assignedTo[]` (users + vendors)
- `dueDate` / `scheduledStart` / `completedDate`
- `estimatedTime` / `actualTime`
- `parts[]` (with quantity)
- `costs[]` (labor, parts, vendor invoices)
- `attachments[]`
- `tags[]`
- `instructions[]` / `checklist[]`
- `linkedPMID` (if recurring)
- Custom fields (via interactive floor plans, fleet fields incl. insurance/warranty/mileage when used for fleet)

**Trade/craft note:** Hippo carries craft as a tag or a custom dropdown; the platform's roots are facility management, so categories like "Fleet" / "Building" / "Grounds" / "IT" are typical defaults.

---

## 14. eWorkOrders

**API:** REST/JSON. Public-facing API; details typically delivered via account-managed onboarding. The work-order data model is conventional facility-CMMS:

- `workOrderID`, `workOrderNumber`
- `title`, `description`, `notes`
- `requesterName`, `requesterEmail`, `requesterPhone`, `requesterDepartment`
- `assetID` (with maintenance history accessible via the asset endpoint), `assetCriticality`
- `locationID`, `building`, `room`/`area`
- `priority`, `status`
- `assignedTo[]`, `team`
- `dueDate`, `scheduledDate`, `startedDate`, `completedDate`
- `craft` / `skill` (configurable)
- `estimatedLaborHours` / `actualLaborHours`
- `parts[]` (with quantity), `tools[]`
- `costs` (labor + parts + service)
- `attachments[]` (photos, schematics, docs)
- `signatures[]` (digital — before / after)
- `customFields[]`
- `tenantPortal` fields when integrated with property-management workflows
- `apiTriggerSource` (when work orders are created automatically from facility automation systems — BAS/BMS, sensor alarms, downtime events)

**Trade/craft note:** eWorkOrders carries an explicit `craft`/`skill` field; trades are configurable per tenant and used both for technician routing and asset/PM template assignment.

---

## 15. FMX (Facilities Management eXpress)

**API:** REST. Maintenance Request module is the canonical WO module; other modules (Tech, Custodial, Key, HR) reuse the same shape.

Default maintenance-request payload (mirrors the create form):

- `requestType` (the FMX module — Maintenance Request, Technology Request, etc.)
- `onBehalfOf` (when a user creates the request for someone else)
- `equipmentID[]` (fixed assets)
- `dueDate`
- `followers[]` (additional users CC'd into status notifications)
- `description`
- `customFields[]` (added by site administrator; can be required or optional)
- `attachments[]` (photos, schematics, etc.)
- `priority` / `status` (configurable)
- `assignedTo[]`
- `building` / `room` / `floor`
- `inventoryItems[]` (consumables used)
- `laborHours`
- `costFields[]` (when integrated with QuickBooks Online — costs and labor are pushed back as invoice line items)

**Trade/craft note:** FMX handles "trade" by giving you a dedicated module per craft (Maintenance, Technology, Custodial, Grounds, etc.) instead of putting a trade column on a single WO entity — so the trade is implicit in the request type rather than carried as a field.

---

## 16. TMA Systems WebTMA

**API:** REST/SOAP available, broadly admin-gated. WebTMA is heavily configurable and tuned for education, healthcare, and multi-site facility operations.

Standard WO header fields:

- `wonum`, `description`
- `requestor`, `requestorPhone`, `requestorEmail`, `dept`
- `assetID` / `equipmentID`, `assetTag`
- `siteID`, `building`, `floor`, `room`
- `priority`, `status`
- `repairType` (TMA's trade/craft equivalent)
- `assignedTo[]`
- `dueDate`, `scheduledStart`, `completedDate`
- `estimatedHours`, `actualHours`
- `parts[]`, `labor[]`, `contractor[]`
- `costObject` (with material/labor/contractor/equipment subtotals)
- `procedureID` (linked task plan)
- `inspectionID`, `capitalPlanID`
- Custom fields, configurable per WO type

**Trade/craft note:** `repairType` (also called "WorkType" / "Trade" depending on the tenant's config) is a first-class lookup-table field.

---

## 17. ManagerPlus (now Eptura Maintain / part of Eptura)

**API:** REST/JSON. Field shape is similar to Hippo / Eptura Asset (same parent company since the Eptura rebrand):

- `workOrderID`, `workOrderNumber`
- `title`, `description`
- `assetID`, `locationID`
- `priority`, `status`, `workOrderType`
- `assignedTo`, `team`, `vendor`
- `requestedDate`, `dueDate`, `completedDate`
- `estimatedCost`, `actualCost`
- `parts[]`, `labor[]`, `meterReadings[]`
- `inspectionItems[]`
- `failureCodes[]`
- `attachments[]`, `signatures[]`
- Custom fields

**Trade/craft note:** Configured per-tenant; ManagerPlus traditionally calls it "Trade" or "Skill" on the technician side, and routes WOs by matching the asset's required-skills array.

---

## 18. MicroMain

**API:** REST/JSON (admin-gated for the SaaS edition). MicroMain has been doing CMMS since 1991, and its work-order schema is one of the most asset-history-rich in the SMB tier.

Typical WO fields:

- `wo_number`, `description`, `long_description`
- `requester`, `request_date`
- `asset_id`, `asset_location`, `system_id` (asset-system hierarchy)
- `priority`, `status`, `workType` (Corrective / Preventive / Inspection / Project)
- `craft` / `trade` (lookup)
- `assignedTo[]`, `crew`
- `scheduled_start`, `scheduled_end`, `actual_start`, `actual_end`, `due_date`
- `estimated_labor_hours`, `actual_labor_hours`, `estimated_cost`, `actual_cost`
- `parts[]`, `tools[]`, `procedures[]`, `safety_steps[]`
- `meter_readings[]`
- `cause_code`, `failure_code`, `action_code`
- `account_code` / `gl_code`
- Custom fields

**Trade/craft note:** Trade is a discrete attribute and is used to filter the technician picker.

---

## 19. Maintenance Connection (Accruent)

**API:** REST. Accruent's WO data model (Maintenance Connection is now part of the Fluke Reliability + Accruent ecosystem in the broader market):

- `workOrderNumber`
- `description`, `longDescription`
- `assetID`, `locationID`, `siteID`
- `priority`, `status`, `workOrderType` (Corrective / PM / Inspection / Project / Safety)
- `tradeID` (explicit field)
- `requestedBy`, `assignedTo[]`, `supervisor`
- `requestedDate`, `dueDate`, `scheduledDate`, `completedDate`
- `estimatedHours`, `actualHours`, `estimatedCost`, `actualCost`
- `procedureID`, `inspectionTemplate`
- `failureClass`, `failureCode`, `causeCode`, `remedyCode`
- `parts[]`, `labor[]`, `contractors[]`
- `costAccount` / `glAccount` / `projectID`
- `meterReadings[]`
- Custom fields, signatures, attachments

**Trade/craft note:** Maintenance Connection ships with a `Trade` field built into the WO header and routes/permissions can be filtered by trade.

---

## 20. FTMaintenance Select, Click Maint, and other SMB platforms (brief)

These have either no public API (FTMaintenance), or a closed/partner-only API (Click Maint, Cheqroom CMMS pre-launch, OxMaint, Maintainly, Tractian), or a generic CMMS shape that mirrors UpKeep / MaintainX. Where they do expose work-order data, the fields are essentially the union of: number, title, description, priority, status, asset, location, assignedTo, dueDate, completedDate, parts, labor, attachments, custom fields, and either `category` or `trade` for the craft field.

The FTMaintenance "anatomy of a work order" guide explicitly lists the canonical SMB shape as: Work Order Number, Requester Information, Asset Information, Location, Problem Description, Instructions, Parts and Materials, plus optional Priority, Labor Craft, Maintenance Type, Risk Level, and Attachments.

---

## The Universal Work-Order Payload — Cross-Platform Synthesis

After mapping all 20 platforms, here is the **common payload** that appears across every modern CMMS, named with the dominant convention. If you're building an integration layer that needs to normalise across these systems, this is the model to start with.

### Identity (every platform)
- **`id`** — system-internal numeric ID
- **`number`** — user-facing work-order number (separate from `id` in Maximo, Brightly, ServiceChannel, Corrigo, SAP, and others)
- **`externalId`** — for ERP/3rd-party correlation (explicit in SAP, custom on most others)

### Descriptive (every platform)
- **`title` / `description` (short)** — required almost everywhere; the only required field on MaintainX
- **`longDescription` / `notes`** — separate field in SAP (`_LongText`), Maximo (`DESCRIPTION_LONGDESCRIPTION`), Brightly (`WorkRequested`), Infor EAM (`commentText`)

### Classification — work type
- **`workType` / `workOrderType` / `maintenanceType`** — Corrective, Preventive, Emergency, Inspection, Project, Capital, Safety. Every platform has this; vocabularies differ but the value set converges.
- **`category` / `categories[]`** — UpKeep, MaintainX use this as a multi-select. Often overlaps with trade.

### Classification — trade / craft (the field the user asked about)
This is the single most inconsistently-named field in the industry. The same concept appears as:

| Platform | Field name |
|---|---|
| IBM Maximo | `WORKTYPE` at the header (work class) + `CRAFT` at the labor line |
| SAP S/4HANA | `MainWorkCenter` (header) + `OperationWorkCenter` (per operation) |
| Oracle eAM | `Department` (header) + `Resource` on each operation |
| Infor EAM | `tradeCode` on the activity (not header) |
| Fiix | `maintenanceType` + skills on user |
| eMaint | configurable `Trade` / `Skill` field |
| Brightly Asset Essentials | `WorkCategory` (explicit "trade" — HVAC, Plumbing, Electrical, etc.) |
| ServiceChannel | `ContractInfo.TradeName` (drives provider routing) |
| Corrigo | `TaskCategory` + `RepairCategory` at completion |
| MaintainX | `Categories[]` |
| UpKeep | `category` |
| Limble | `customTags` (typically "Trade") |
| Hippo | category / tag |
| eWorkOrders | `craft` / `skill` |
| FMX | implicit in the request type / module |
| TMA WebTMA | `repairType` |
| ManagerPlus | configurable `Trade` |
| MicroMain | `craft` / `trade` (explicit) |
| Maintenance Connection | `tradeID` (explicit) |
| FTMaintenance | optional `Labor Craft` |

**Practical takeaway:** if you're integrating across platforms, map every vendor's "trade-like" field into a single canonical `tradeCode` in your middleware, and keep a per-vendor mapping table — there is no shortcut here.

### Priority (every platform)
Numeric scale (1–5 or 5/10/15/20/25 on SAP) **or** named (P1 EMERGENCY / P2 8HR / P3 24HR / P4 72HR / P5 WEEK on ServiceChannel; Critical / High / Medium / Low / None on most others). Lookup-table-driven and configurable on every modern platform.

### Status (every platform)
The lifecycle phases are remarkably consistent: a `Requested/New` state → an `Approved/Released` state → an `Active/InProgress` state → optional `OnHold/Waiting` states (Maximo has WAPPR, WMATL, WSCH) → `Completed` → `Closed/Cancelled`. SAP uses `MaintOrdProcessPhaseCode` 01–09 plus separate `SystemStatus`/`UserStatus`. Maximo uses single-token codes. Most modern platforms use a configurable workflow.

### Asset, location & site (every platform)
- **`assetId` / `equipmentId`** — usually optional, often required for PMs
- **`locationId` / `functionalLocation`** — required almost everywhere
- **`siteId` / `plant` / `subscriberId` / `organization`** — required for multi-site tenants
- **Linear-asset support** (Infor EAM, Maximo, Brightly) — fromPoint, toPoint, direction
- **GIS coordinates** — Brightly, ServiceChannel (check-in coords), Corrigo (technician GPS)

### People & assignment (every platform)
- `requestedBy` / `reportedBy` / `caller` / `originator`
- `assignedTo` (single user OR multi-user array — MaintainX, Limble, Fiix support both)
- `team` / `crew`
- `vendor` / `provider` (and Provider Rank for multi-vendor routing — ServiceChannel)
- `supervisor` / `personResponsible` / `planner`
- `followers[]` (FMX)

### Schedule (every platform)
- `requestedDate` / `callDate` / `reportDate`
- `targetStart` / `targetCompletion`
- `scheduledStart` / `scheduledFinish`
- `actualStart` / `actualFinish`
- `dueDate` (suggestedCompletion in Fiix)
- `estimatedDuration` / `actualDuration`

### Cost & financial (every platform with a costing module)
- `estimatedLaborCost` / `actualLaborCost`
- `estimatedLaborHours` / `actualLaborHours`
- `estimatedMaterialCost` / `actualMaterialCost`
- `estimatedToolCost` / `actualToolCost`
- `estimatedServiceCost` / `actualServiceCost`
- `nte` (not-to-exceed — ServiceChannel, Corrigo, Maintenance Connection)
- `glAccount` / `costCode` / `costCenter` / `project` / `task`
- `currency`

### Failure model (asset-intensive industries)
- `problemCode`, `failureCode`, `causeCode`, `remedyCode` / `actionTaken`, `failureClass` — Maximo, Infor EAM, Oracle eAM, Maintenance Connection, ServiceChannel, Corrigo, MicroMain all carry these as a first-class taxonomy. UpKeep, MaintainX, Limble, Fiix expose them as configurable custom fields or tags.

### Work plan / procedure (every platform)
- `procedureId` / `taskPlanId` / `jobPlanNumber` / `standardWorkOrder`
- `tasks[]` / `instructions[]` / `checklist[]` / `procedureSteps[]` — each step typically has its own ID, label, description, response type (text / number / pass-fail / signature / image / meter reading), required flag, and (in modern systems) anomaly-detection or pass/fail/flag state.

### Resources used (every platform)
- `parts[]` — each with partId, quantityUsed, unitCost (often override-able), location (when multi-location-parts is enabled)
- `labor[]` / `laborBookings[]` — each with user/employee, trade/craft, hours, rate, start/end, billable flag
- `tools[]`
- `services[]` / `contractors[]` — vendor, invoice number, amount

### Attachments & evidence (every platform)
- `attachments[]` — files, photos, videos, schematics, manuals
- `pictures[]` (often separate from attachments — MaintainX, UpKeep)
- `signatures[]` — digital sign-off (eMaint, eWorkOrders, Brightly, Maintenance Connection)
- `requiredDocuments[]` (Corrigo's typed slots)

### Meter & downtime (asset-intensive industries)
- `meterReadings[]` — meterId, reading, units, timestamp
- `assetDown` / `MaintenanceObjectIsDown` (SAP) — boolean
- `downtimeStart` / `downtimeEnd` / `downtimeHours` / `downtimeCost`

### Audit (every platform)
- `createdBy` / `createdAt` / `updatedBy` / `updatedAt` / `changedBy` / `changedOn`
- `source` — channel that created the WO (dashboard, IVR, API, sensor, email, mobile, web)

### Custom fields (every modern platform)
Either:
- a typed `customFields[]` array (UpKeep, Brightly, MaintainX, Limble, Corrigo, ServiceChannel `AdditionalFields`, Hippo), or
- pre-allocated `UDF1`…`UDFn` columns (Infor EAM, legacy systems), or
- a fully configurable form (eMaint, Maintenance Connection, MicroMain)

### Webhooks (modern platforms)
Limble, Fiix, MaintainX, UpKeep, ServiceChannel, Corrigo all publish webhooks. The minimum payload is always: `{ id, status, category, user, timestamp }`. The richest webhook is ServiceChannel's — the full work-order object is pushed on every state transition.

---

## Pragmatic Recommendations for Integration Builders

1. **Build to the union, not the intersection.** The intersection of all 20 schemas is small (number, title, asset, location, priority, status, assignedTo, dueDate, completedDate); the union is hundreds of fields. Define your canonical model as the union and accept that any given vendor will only populate a subset.

2. **Treat trade/craft as a per-vendor mapping problem.** There is no industry standard. Maintain a vendor-by-vendor mapping table from your canonical `tradeCode` to each vendor's local field — `WORKTYPE`, `MainWorkCenter`, `WorkCategory`, `TradeName`, `Category`, `Categories[]`, `craft`, `tradeID`, `repairType`, `tradeCode`, or in some cases a custom field / tag.

3. **Expect priority to be numeric *or* named.** SAP uses 5/10/15/20/25. Maximo uses 1–5. ServiceChannel uses `P1`-`P5` with SLA verbs ("P2 - 8 Hours"). Don't hard-code; pull the priority master from each tenant.

4. **Don't conflate `id` and `number`.** Brightly, Maximo, SAP, Corrigo, and ServiceChannel all separate the system identifier from the user-facing work-order number. Storing only the number in your middleware will break when a customer renames a WO to match an ERP reference.

5. **Lifecycle states are not portable.** Map every vendor's status set to your own canonical lifecycle (Draft → Approved → Scheduled → InProgress → OnHold → Completed → Closed → Cancelled) — every vendor has its own state machine and the codes don't line up.

6. **Custom fields, custom fields, custom fields.** In production, the customer-specific custom fields will outnumber the standard fields on virtually every WO. Build your integration to discover them (e.g. `GET /custom-fields/workorders` on UpKeep, `customFields[]` on the WO object in Brightly, UDF columns in Infor EAM) and pass them through as typed objects.

7. **Long descriptions belong in their own field.** Maximo, SAP, Infor EAM, and Brightly all separate the short description (40–255 chars) from the long description (multi-KB rich text). Trying to stuff everything into one field will silently truncate.

8. **UTC everywhere.** Brightly explicitly recommends setting the API user to UTC; ServiceChannel requires UTC `CallDate`; SAP returns date-times in milliseconds-since-epoch on V2 OData and ISO 8601 on V4. Centralise time-zone handling in middleware.

---

*Sources: each vendor's developer portal (IBM Maximo OSLC REST docs, SAP Business Accelerator Hub, Oracle eAM Work Management user guide, Infor EAM Swagger + samaconsultinginc field reference, fiixlabs.github.io, developers.onupkeep.com, help.getmaintainx.com + maintainx.dev, apidocs.limblecmms.com, help.brightlysoftware.com, developer.servicechannel.com, developer.corrigo.com + developer.corrigopro.com, emaint.com docs, eworkorders.com integration docs, gofmx.com, ftmaintenance.com knowledge base, tmasystems.com, eptura.com / hippocmms.com), supplemented by Pipedream / Make / Makini / Supergood / Ibexa Connect integration-platform field references where vendor docs are gated.*
