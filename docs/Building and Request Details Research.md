# **Architectural Analysis of Data Retrieval Mechanisms for Building and Request Metadata: A Cross-Domain Study of Municipal, Judicial, and Enterprise Systems**

## **1\. Introduction: The Dual Nature of Asset Intelligence**

In the contemporary landscape of public administration and enterprise resource planning, the digital representation of physical assets—specifically "Building Details"—and the transactional workflows associated with them—"Request Details"—forms the backbone of operational efficiency. The retrieval of this data is rarely a singular event; rather, it is a complex navigation through bifurcated systems where administrative portals manage the "process" (requests) and geospatial or facility management systems manage the "place" (buildings).

This report provides an exhaustive technical analysis of where and how to obtain these specific data points. By synthesizing a diverse array of technical documentation, user manuals, and architectural specifications, we have identified two primary ecosystems that serve as the case studies for this analysis: the **Muscat Municipality** in the Sultanate of Oman, representing a modern, integrated municipal governance model; and the **California Judicial Branch** in the United States, representing a highly regulated, federated facility management environment. Furthermore, we examine the underlying enterprise software layers—specifically **Oracle Identity Manager**, **ServiceNow**, and specialized banking platforms—that provide the technical scaffolding for these data interactions.

The analysis reveals that "Building Details" are typically static or semi-static attributes residing in asset registries, GIS layers, or master data records, encompassing fields such as occupancy type, plot numbers, and architectural footprints. Conversely, "Request Details" are dynamic, transactional records generated during workflows such as permit applications, lease negotiations, urgent facility repairs, or identity provisioning. The effective extraction of this information requires a nuanced understanding of user interface (UI) workflows, backend database schemas, and Application Programming Interface (API) endpoints.

## **2\. The Muscat Municipality Ecosystem: Geospatial and Administrative Convergence**

The digital transformation of the Muscat Municipality has resulted in a high-fidelity integration of administrative e-services with geospatial information systems (GIS). Retrieval of "Building Details" and "Request Details" in this context is heavily dependent on the interaction between the Baladiety portal, the internal building permit systems, and the public-facing ArcGIS REST endpoints.

### **2.1 The Administrative Layer: Retrieving "Request Details" via e-Services**

Within the Muscat Municipality's digital infrastructure, "Request Details" are inextricably linked to the lifecycle of municipal permits and contracts. These details are not merely static descriptions but are active components of a workflow that involves initiation, payment, inspection, and approval.

#### **2.1.1 The Service Request (SR) Architecture**

The primary vessel for "Request Details" is the Service Request (SR). According to the user manuals for the municipality’s iSupport and Rent Contract systems, the retrieval of these details follows a strict user journey. When a user—defined as a consultant, individual owner, or corporate entity—initiates a transaction, the system generates a unique Service Request number.

Retrieval Location: The Service Request Inquiry Screen  
The comprehensive "Request Details" are located on a dedicated page accessible via the dashboard of the e-Services portal. The navigation path requires the user to access the "Companies request" or "Individual request" homepage \[1, 2\].

* **Mechanism:** The user must identify the specific SR number or invoice number associated with their transaction. Clicking the "View" link or the invoice number triggers the "Request Details" page \[3\].  
* **Data Composition:** The page serves as an aggregator of both financial and administrative metadata. It displays:  
  * **Invoice Metadata:** Invoice Number, Invoice Date, Invoice Amount, and Transaction Number. This financial data is critical for validating that a request has moved from the "submitted" phase to the "processing" phase \[3\].  
  * **Workflow Status:** The interface provides real-time status updates, such as "Service Request Rejected Successfully" or payment confirmation. It also links to the "Invoice Review" page, which is a sub-component of the request details focusing solely on the fiscal transaction \[1, 3\].

#### **2.1.2 The Consultant Report Details Interface**

For construction and engineering stakeholders, the general SR screen is insufficient. A deeper level of "Request Details" is available in the "Consultant Report Details" section (specifically noted as Page 44 in the system documentation) \[3\].

This specific interface acts as a bridge between the financial request and the technical building data. It allows the user to view reports that have been generated as part of the request lifecycle.

* **Integration Point:** The system allows users to "Forward to Muscat Municipality," indicating that the "Request Details" screen is also an input form for state transitions, moving the data from the external consultant's domain into the internal municipal approval queue \[3\].  
* **Rent Contract Specifics:** In the specific case of rent contracts, the "Request Details" expand to include "Units New Rental Details." This block displays tax, fine, and total value calculations, and importantly, allows for the creation of a new Service Request for cancelled contracts \[1\]. This demonstrates that in the Muscat system, a "Request Detail" view can inextricably spawn *new* requests, creating a linked chain of data records.

### **2.2 The Geospatial Layer: Retrieving "Building Details" via ArcGIS and GIS APIs**

While the administrative portal handles the *process*, the *physical reality* of the buildings is managed through a sophisticated GIS implementation powered by Esri technologies. For researchers, developers, or city planners, the most exhaustive source of "Building Details" is not the web forms, but the ArcGIS REST API endpoints.

#### **2.2.1 The Buildings\_2022 Feature Layer**

The municipality exposes a dedicated feature layer named Buildings\_2022 (Layer ID: 9), hosted on the mmedms.mm.gov.om server. This API endpoint is the definitive source of truth for the physical attributes of structures within the governorate \[4, 5\].

Technical Access Point:  
The data is retrievable via the following REST endpoint:  
https://mmedms.mm.gov.om/server/rest/services/GIS\_API/GIS\_Map\_APIs/MapServer/9  
Schema and Attribute Definitions:  
The JSON response from this endpoint provides a rich set of "Building Details" that extends far beyond the basic descriptors found in the permit application forms. A query to this endpoint yields a feature collection where the attributes object contains the following critical fields:

| Field Name | Description & Strategic Insight | Source |
| :---- | :---- | :---- |
| PlotUID | **System Unique Identifier.** This is the primary key used to join building geospatial data with administrative databases. It is system-generated and immutable. | \[4\] |
| DirectorateCD | **Directorate Code.** This integer code represents the administrative jurisdiction (e.g., Mutrah, Seeb). It is essential for filtering data by governance zones. | \[4\] |
| KrookiNo | **Plot Sketch Number.** In the context of Omani property law, the "Krooki" is the definitive legal document of land ownership. Its presence in the API allows for cross-referencing with the Ministry of Housing. | \[4\] |
| PermitType | **Classification.** Distinguishes between "Major" and "Minor" permits. This field allows analysts to separate large infrastructure projects from small residential modifications. | \[4, 5\] |
| PlotArea | **Spatial Metric.** The total area of the land plot. This serves as the denominator for calculating build-up density. | \[4\] |
| Flag | **Ownership Indicator.** Values include MM (Muscat Municipality) or PB (Public), instantly identifying government-owned versus private assets. | \[4\] |
| PermitYear | **Temporal Marker.** The year of issuance, enabling time-series analysis of urban development. | \[4, 5\] |

Usage Protocol:  
To obtain this data, one must construct a query operation on the REST endpoint. The system supports parameters such as where (SQL syntax), outFields (to specify attributes like KrookiNo), and f (format, typically json or pbf). The layer is configured with a MaxRecordCount of 1000, implying that full-city retrieval requires pagination logic \[4\].

#### **2.2.2 The "Permits" Layer and Footprint Data**

Complementing the 2022 building layer is the "Permits" layer (often found in map services like Mutrah\_Directorate\_Map\_Service\_MIL1). This layer, specifically described in the research as representing "footprints of buildings that have been granted permits," offers a geometric representation of the "Building Details" \[6\].

* **Semantic Nuance:** Unlike the Buildings\_2022 layer which might represent existing stock, this layer represents *permitted* construction. It links the physical polygon of the building footprint to the "Request Details" of the permit, creating a spatial-temporal record of authorized development.  
* **Coordinate Systems:** The data is available in geoJSON and PBF, and supports standard spatial references (WGS84 implied by the mention of "NewPlotNo" adjustments) \[4\].

### **2.3 The Open Data Portal: Flat-File Retrieval**

For users without the technical capability to query REST APIs, the Muscat Municipality Open Data Portal offers a static, bulk-download alternative. The research highlights several key datasets that contain "Building Details" and "Request Details" in XLSX and XLS formats \[7\].

**Key Datasets for Retrieval:**

1. **Construction Permit Dataset:**  
   * **Data Points:** Permission date, Number of floors, Buildup area, Address.  
   * **Relevance:** This dataset bridges the gap between the "Request" (Permission date) and the "Building" (Number of floors, Buildup area). It is segmented by region (e.g., Quryat, Bowsher) \[7\].  
2. **Building Permit Dataset:**  
   * **Data Points:** Service type, Type of use, Address.  
   * **Relevance:** This provides the functional classification ("Type of use") which is critical for zoning analysis \[7\].  
3. **Rent Contract Dataset:**  
   * **Data Points:** Rent Contract Type, Contract Status, Activity name and code (ISIC 4).  
   * **Relevance:** While primarily transactional, the "Activity name" acts as a proxy for the building's commercial usage detail \[7\].

### **2.4 User Interface Data Entry for "Building Details"**

Within the e-Services portal, "Building Details" are not just read-only; they are actively constructed by users during the application process. The "Add, edit and delete buildings" functionality allows users to input specific descriptors into a grid format \[3\].

* **Input Fields:** Users manually enter the "Description of the building," "Type of building," and "Type of use."  
* **Hierarchical Structure:** Uniquely, the system enforces a parent-child relationship where "Floors" are attached to a selected "Building." This means "Building Details" in this system are composite objects containing nested "Floor Details," which must be retrieved by expanding the building record in the grid interface \[3\].

## **3\. The California Judicial Branch Ecosystem: Facility Management and Fiscal Oversight**

In contrast to the municipal model of Oman, the California Judicial Branch manages "Building Details" and "Request Details" through a prism of centralized facility management and fiscal oversight. The primary systems involved are the **Computer Aided Facilities Management (CAFM)** system (powered by IBM TRIRIGA) and the **Court Funded Request (CFR)** workflow. The objective here is not permit issuance, but rather the maintenance, leasing, and operational continuity of court facilities.

### **3.1 The Court Funded Request (CFR) Mechanism**

The "Request Details" in the California system are highly specific to fiscal approvals for facility maintenance, leasing, and urgent repairs. These are captured in the "Court Funded Request Details" section of the application, which serves as a governance gate for spending \[8\].

#### **3.1.1 Structure and Retrieval of a CFR**

The "Request Details" are structured as a dynamic questionnaire designed to categorize the urgency and nature of the funding requirement. To obtain the full "Request Details," one must access the responses to "Question 1" in the CFR section.

Detailed Taxonomy of a Request:  
The system mandates a selection from specific categories that define the "Request Detail":

1. **Nature of Urgent Request:** This is the primary classifier.  
   * *Lease-related cost (excluding records storage)*  
   * *Lease for records storage only*  
2. **Conditional Cost Breakdown:** The system exhibits intelligent behavior where selecting "Lease-related cost" triggers the display of further checkboxes:  
   * *Lease costs only*  
   * *Lease costs including tenant improvement costs* \[8\].

Operational Insight:  
Retrieving "Request Details" in this context is essentially retrieving the justification for expenditure. The distinction between "Lease costs only" and "Lease costs including tenant improvement" is a critical data point for auditing facility spend. This data is likely stored in a transactional table linked to the Request\_ID in the underlying Oracle database, and accessible via the application's reporting module.

### **3.2 CAFM and the Master Building Record**

The "Building Details" within the California Courts system are managed centrally to ensure consistent reporting across the Supreme Court, Courts of Appeal, and trial courts \[9\]. The research indicates that "Building Details" are not just static records but are actively used to populate downstream financial systems, specifically Utility Account Management.

#### **3.2.1 Auto-Population and the Source of Truth**

According to the business and technical requirements, the system is designed to **auto-populate** "Building Details" from a master building record into other sections of the application, such as the Utility Account section \[8\]. This architectural decision confirms that the "Master Building Record" is the single source of truth.

Retrievable Building Attributes:  
When accessing the Utility Account section or the Building Record directly, the following "Building Details" are mandated ("1-Must Have"):

* **Bldg ID:** The unique alphanumeric identifier for the facility.  
* **Bldg Name:** The official designation of the courthouse or facility.  
* **Bldg Status:** Operational status (e.g., Active, Decommissioned, Leased).  
* **Address Fields:** Address, City, County, Zip Code.  
* **Occupancy Type:** A critical classification field (e.g., Courthouse, Holding Cell, Administrative, Storage) that determines funding eligibility and security levels \[8\].

Service Account Linkage:  
The system also links "Building Details" to "Service Account" information. When retrieving data for a specific building, one can also expect to find associated utility metadata:

* Utility Account Number  
* Service Account Number  
* Meter ID  
* Container ID \[8\].

### **3.3 Integration Infrastructure: TIBCO ISB and SOAP APIs**

Accessing these details programmatically requires navigating the **Integrated Service Backbone (ISB)**. The California Courts Technology Center (CCTC) utilizes a TIBCO-based ISB to mediate data exchange between the central CAFM system, the document management systems (DMS), and local court interfaces \[10, 11\].

#### **3.3.1 API Protocols for Data Retrieval**

For systems integrators or internal IT staff, "Building Details" and "Request Details" are exposed via enterprise-grade web services.

* **Protocol:** The preferred method for retrieval is via **SOAP 1.2** and **WSDL** based interfaces. The system utilizes J2EE and Java APIs \[10, 11\].  
* **Data Exchange Format:** The system supports **CMIS** (Content Management Interoperability Services) for document-related request details, ensuring that attachments (like lease agreements or repair photos) are retrievable in a standard format \[11\].  
* **Security Layer:** Access is strictly governed by the **Oracle Security Suite**. Any API call to fetch building data must be authenticated against **Oracle Access Manager (OAM)** and **Oracle Internet Directory (OID)**. This implies that "Building Details" are not public data (unlike in Muscat) but are protected enterprise assets \[11\].

#### **3.3.2 Document Management Context**

The "Request Details" often include unstructured data (documents). The research highlights that the courts utilize an enterprise-level EMC solution and various DMS. The "Request Details" retrieval process must therefore include calls to the DMS via the ISB to fetch the *content* of the request (e.g., the scanned PDF of the lease) in addition to the metadata \[10, 12\].

## **4\. Enterprise Identity and Service Management Layers**

Beyond the specific business logic of municipalities and courts, the research reveals that "Building Details" and "Request Details" are often encapsulated within broader enterprise management platforms like **Oracle Identity Manager (OIM)**, **ServiceNow**, and specialized banking software. These systems provide the "plumbing" for data retrieval.

### **4.1 Oracle Identity Manager (OIM): The Task Flow Architecture**

In an Oracle-based environment (referenced in both the California and general enterprise contexts), "Request Details" are often managed as "Task Flows."

The request-details-tf Task Flow:  
The research identifies a specific XML configuration file, request-details-tf.xml, which is responsible for rendering the details of a request submitted for approval \[13\].

* **Retrieval Mechanism:** To view these details, the system launches the request-details-tf task flow.  
* **Input Parameter:** The critical input required is the requestID. Without this ID, the task flow cannot instantiate the details view \[13\].

Building Details in Provisioning Tasks:  
Interestingly, OIM also utilizes "Building Details" pages for manual fulfillment tasks. The research specifies that for "Disconnected Provisioning" or "Manual Provisioning," a specific task flow (DisconnectedProvisioning/ManualProvisioningTask.task) is used.

* **Configuration:** Developers must unzip specific archives (e.g., DefaultRequestApproval.zip or DisconnectedProvisioning.zip) to access and customize the "Building Details" page structure \[13\]. This highlights that in OIM, "Building Details" might refer to the *details of building an identity* or a specific resource allocation, rather than a physical structure, though the terminology overlaps.

### **4.2 Banking and Retail Account Systems**

In the context of Oracle Banking and Financial Services (referenced in snippets \[14\], \[15\], \[16\]), "Building Details" take on a specific role in **Know Your Customer (KYC)** and address verification.

Communication Address Schema:  
When a user updates an account or submits a service request in these systems, "Building Details" are a subset of the Communication Address.

* **Fields:** Building Name/Details, Street Name, City/Town, State, Country.  
* **Retrieval Logic:** The system displays the *current* building details derived from the function ID STDSRQST (Service Request Input screen). Users can edit these details, meaning the "Building Detail" is mutable and transactional within the scope of a Service Request \[16\].  
* **Account Closure Requests:** Specific "Request Details" are also generated for account closures, displaying the latest closure request details if multiple exist (e.g., close and reopen cycles) \[14, 15\].

### **4.3 ServiceNow and Workplace Space Mapping**

The research also touches upon **ServiceNow’s Workplace Space Mapping** capabilities \[17\]. Here, "Building Details" are imported from external mapping providers (like Mappedin) to create a digital twin of the workplace.

* **Retrieval Process:** Users use the "Import a new building" function to fetch Mappedin maps. The "Building Details" (e.g., floor plans, room names) are then defined within the ServiceNow record.  
* **Request Details Integration:** ServiceNow allows for the configuration of "Contract Request Forms" where request details are displayed, and contract documents are grouped by type. This links the physical building map to the legal request details \[17\].

## **5\. Third-Party and Peripheral Systems**

The research landscape includes references to several niche systems that manage these details in specific contexts, such as mortgage processing and office scheduling.

### **5.1 Calyx Point (Mortgage Software)**

In the Calyx Point ecosystem, "Building Details" and "Request Details" are part of the loan origination workflow \[18\].

* **Building Details:** Located on page 280 of the user guide, these details likely refer to the property appraisal data.  
* **Request Details:** Specifically linked to the "VA Request for Certificate of Eligibility (26-1880)." Retrieving these details involves entering the Date of Assignment and Appraiser details, highlighting that in this domain, the "Request" is a federal eligibility check \[18\].

### **5.2 Robin (Office Scheduling)**

Robin, a workplace experience platform, treats "Building Details" as configuration metadata for scheduling \[19\].

* **Attributes:** Working hours, Timezone, Address.  
* **Retrieval:** These are added during onboarding and can be retrieved via the admin dashboard.  
* **Ticket Integration:** Robin links "Request Details" (tickets) to these buildings. Users can "View request details" by clicking a blue ticket link, or export the ticket logs to CSV/PDF. This allows for the extraction of data regarding "abandoned meeting protection" or desk usage policies linked to a specific building \[19\].

## **6\. Comparative Taxonomy and Data Schema Analysis**

To assist in the normalization of data extraction across these disparate systems, the following comparative matrices map the "Building Details" and "Request Details" found in the Muscat Municipality context against those in the California Courts and Enterprise contexts.

### **6.1 Building Details Comparison**

| Feature | Muscat Municipality (GIS/Portal) | California Courts (CAFM) | Oracle Banking/OIM |
| :---- | :---- | :---- | :---- |
| **Primary ID** | PlotUID, KrookiNo | Bldg ID | Address Line 1, Building Name |
| **Source System** | ArcGIS Server, Baladiety Portal | TRIRIGA, Oracle DB | Flexcube, OIM Taskflow |
| **Spatial Data** | Polygon Geometries, Plot Area | Address, County, Zip | Street, City, State |
| **Classification** | PermitType (Major/Minor), UseType | Occupancy Type (Courthouse/Storage) | Communication Address Type |
| **Mutability** | Semi-Static (Requires Permit to change) | Static (Master Record) | Mutable (User Edit via SR) |
| **Sub-Components** | Floors (Nested Grid) | Service/Utility Accounts | N/A |

### **6.2 Request Details Comparison**

| Feature | Muscat Municipality | California Courts (CFR) | ServiceNow / Robin |
| :---- | :---- | :---- | :---- |
| **Trigger** | Permit Application, Rent Contract | Lease Funding, Urgent Repair | Contract Request, Help Desk Ticket |
| **Key Metadata** | Invoice \#, Transaction \#, SR Status | Request Nature (Lease/Storage), Cost | Ticket ID, Request Date, Assignee |
| **Approval Flow** | Forward to Municipality \-\> Pay \-\> Permit | Court User \-\> Question 1 \-\> Approval | Submission \-\> Assignment \-\> Resolution |
| **Documents** | Consultant Report, Krooki Sketch | Lease Agreement (CMIS) | Contract Documents (PDF) |
| **Retrieval UI** | "View" Link on Dashboard, Invoice Review | "Court Funded Request Details" Tab | "View request details" Link |

## **7\. Strategic Recommendations for Data Retrieval**

Based on the architectural analysis, we propose the following strategic workflows for obtaining "Building Details" and "Request Details" depending on the target environment.

### **7.1 For Geospatial Analysts (Oman Context)**

* **Action:** Do not rely on the manual e-Services portal for bulk data.  
* **Strategy:** Implement a Python or JavaScript client to query the Buildings\_2022 REST API (MapServer/9).  
* **Key Filters:** Use the DirectorateCD to partition data and the PermitYear to filter for recent developments.  
* **Data Enrichment:** Cross-reference the KrookiNo obtained from the API with the "Construction Permit" XLSX files from the Open Data Portal to append "Permission Date" and "Floor Count" to the spatial polygons.

### **7.2 For Facility Auditors (California Context)**

* **Action:** Focus on the variance between "Lease costs only" and "Tenant improvement costs."  
* **Strategy:** Access the CAFM system via the Oracle-secured web interface. Navigate to the "Court Funded Request Details" section and export the data for "Question 1."  
* **Verification:** Cross-check the "Bldg ID" in the request against the Master Building Record in the Utility Account section to ensure the funds are being requested for a valid, active facility with the correct "Occupancy Type."

### **7.3 For Systems Integrators (Enterprise Context)**

* **Action:** Standardize the "Building Detail" schema.  
* **Strategy:** When integrating Oracle OIM or Banking modules, map the "Building Name" and "Address" fields to the STDSRQST function ID. Ensure that the requestID is passed correctly to the request-details-tf task flow to ensure the UI renders the correct transaction history.  
* **Automation:** Utilize the TIBCO ISB (in the case of CA Courts) or standard REST APIs (in the case of Muscat) to decouple the frontend presentation from the backend data, allowing for the creation of unified dashboards that display both the physical status of a building and the financial status of its requests.

## **8\. Conclusion**

The "Building Detail" and the "Request Detail" are fundamental atoms of administrative data, yet their retrieval is governed by the specific laws of the digital universe they inhabit. In Muscat, the data is **geocentric**, tied to the land and the permit, retrievable via open maps and transparent transaction logs. In California, the data is **fiscal-centric**, tied to the lease and the ledger, protected by enterprise security suites and rigorous approval hierarchies.

To successfully navigate these systems, one must move beyond the surface-level labels and understand the deep structures—the PlotUIDs, the request-details-tf.xml configurations, and the DirectorateCDs—that truly define where the information lives. Whether through a JSON query to a map server or a SOAP call to a facility management bus, the data is available to those who possess the architectural map to find it.