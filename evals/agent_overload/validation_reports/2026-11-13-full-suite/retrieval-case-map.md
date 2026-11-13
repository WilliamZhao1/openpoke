# Retrieval request-to-scenario map, 2026-11-13

These are executed offline queries, not live-model decisions. Each legacy query was run against three rankers at 100/1,000/10,000 workers, with three timing repetitions. Each discovery-v2 query was run against three rankers over the shared 100-worker base plus three draws each at 1,000 and 10,000 workers, with one timing repetition. Repeated draws and timing samples are not extra independent scenarios.

## Original retrieval set — 16 requests / 144 rows

| Request ID | Split / scenario type | Actual request | Expected relevant owners |
| --- | --- | --- | --- |
| exact-lunch | development / single | Alice lunch | Alice lunch |
| original-contract | development / single | Acme original services redline | Alice Acme contract |
| old-taxes | development / single | Morgan 2023 filing | 2023 tax documents |
| atlas-review | development / single | Atlas authentication pull request | GitHub review |
| new-garden | development / none | garden landscaping | (none) |
| acme-ambiguity | development / ambiguous | Alice Acme | Alice Acme contract; Alice Acme renewal; Acme amendment |
| cafe-invitation | evaluation / single | Cafe Etoile invitation | Alice lunch |
| services-owner | evaluation / single | original Acme services | Alice Acme contract |
| dormant-documents | evaluation / single | 2023 documents Morgan | 2023 tax documents |
| expense-owner | evaluation / single | Uber expense reimbursement | Uber receipts |
| repository-owner | evaluation / single | Atlas repository authentication | GitHub review |
| renewal-owner | evaluation / single | Alice renewal terms | Alice Acme renewal |
| amendment-owner | evaluation / single | Acme signed amendment | Acme amendment |
| new-science | evaluation / none | quasar astrophysics | (none) |
| two-topics | evaluation / multiple | Cafe Etoile Acme original services | Alice lunch; Alice Acme contract |
| contract-ambiguity | evaluation / ambiguous | Alice contract | Alice Acme contract; Alice Acme renewal |

## Discovery-v2 — 200 requests / 4,200 rows

There are 20 families: 50 development requests and 150 evaluation requests in disjoint families. Insufficient-metadata requests remain diagnostic and are excluded from primary metrics. No-match requests have no owner-recall denominator. Ambiguous owner coverage does not authorize dispatch or prove clarification quality. Independent semantic label review remains pending.

| Request ID | Split / category / answerability | Actual request | Expected relevant owners |
| --- | --- | --- | --- |
| vendor:exact_name | development / exact_name / answerable | Beacon licenses 2026 | Beacon licenses 2026 |
| vendor:description | development / description / answerable | Who is handling the double payment for Northstar Beacon? | Northstar / Beacon duplicate charge |
| vendor:paraphrase | development / paraphrase / answerable | Find the owner checking whether the Beacon supplier at Northstar meets our protection requirements. | Beacon vendor assurance |
| vendor:same_entity | development / same_entity / answerable | For Northstar Beacon, continue getting the new team onto the workspace rather than changing the subscription. | Getting Beacon seats ready |
| vendor:period_artifact | development / period_artifact / answerable | Pick up the Northstar Beacon license agreement for 2027, rather than the 2026 one. | Beacon licenses 2027 |
| vendor:dormant | development / dormant / answerable | Find the older Northstar Beacon 2026 subscription work that Maya Chen filed. | Beacon licenses 2026 |
| vendor:multiple | development / multiple / answerable | I need both the duplicate-invoice refund and the new-staff invitations for Northstar Beacon. | Northstar / Beacon duplicate charge; Getting Beacon seats ready |
| vendor:ambiguous | development / ambiguous / ambiguous | Which workers handle Northstar Beacon license renewals? I have not specified a year. | Beacon licenses 2026; Beacon licenses 2027 |
| vendor:no_match | development / no_match / answerable | Start arranging an art auction for Northstar Beacon; which existing worker owns that? | (none) |
| vendor:insufficient_metadata | development / insufficient_metadata / insufficient_metadata | Find the worker associated with private receipt QX-VENDOR-48. | Beacon vendor assurance |
| travel:exact_name | development / exact_name / answerable | Meridian rail passes 2026 | Meridian rail passes 2026 |
| travel:description | development / description / answerable | Locate the Brookhaven Meridian train-delay reimbursement work. | Meridian missed connection claim |
| travel:paraphrase | development / paraphrase / answerable | Who was ensuring travelers on Brookhaven Meridian could reach their hotel rooms without stairs? | Accessible Meridian stays |
| travel:same_entity | development / same_entity / answerable | Continue the meeting-space arrangements for Brookhaven Meridian, not transport or lodging. | Meridian workshop rooms |
| travel:period_artifact | development / period_artifact / answerable | I mean the Brookhaven Meridian railway booking for 2027, not the previous year. | Meridian rail passes 2027 |
| travel:dormant | development / dormant / answerable | Reopen Omar Haddad’s older Brookhaven Meridian 2026 train-pass arrangement. | Meridian rail passes 2026 |
| travel:multiple | development / multiple / answerable | Bring back the Brookhaven Meridian missed-connection claim and workshop room booking. | Meridian missed connection claim; Meridian workshop rooms |
| travel:ambiguous | development / ambiguous / ambiguous | Show the owners of Brookhaven Meridian train-pass bookings across the two years. | Meridian rail passes 2026; Meridian rail passes 2027 |
| travel:no_match | development / no_match / answerable | We need a new Brookhaven Meridian employee pension review; does any worker own it? | (none) |
| travel:insufficient_metadata | development / insufficient_metadata / insufficient_metadata | Locate the owner of confidential ticket QX-TRAVEL-51. | Accessible Meridian stays |
| legal:exact_name | development / exact_name / answerable | Juniper lease — 2026 | Juniper lease — 2026 |
| legal:description | development / description / answerable | Who has the Harbor Legal Juniper landlord-deposit dispute? | Juniper deposit recovery |
| legal:paraphrase | development / paraphrase / answerable | Find the Harbor Legal Juniper owner checking who may see confidential supplier information. | Juniper access terms |
| legal:same_entity | development / same_entity / answerable | Harbor Legal Juniper needs the signing meeting coordinated, not another contract review. | Juniper signature appointment |
| legal:period_artifact | development / period_artifact / answerable | Continue the Harbor Legal Juniper tenancy extension for 2027 specifically. | Juniper lease — 2027 |
| legal:dormant | development / dormant / answerable | Find Elena Rossi’s archived Harbor Legal Juniper 2026 rental agreement work. | Juniper lease — 2026 |
| legal:multiple | development / multiple / answerable | Get the deposit-recovery and signing-appointment workers for Harbor Legal Juniper. | Juniper deposit recovery; Juniper signature appointment |
| legal:ambiguous | development / ambiguous / ambiguous | Find the workers for Harbor Legal Juniper office-lease renewals without choosing a year. | Juniper lease — 2026; Juniper lease — 2027 |
| legal:no_match | development / no_match / answerable | Assign Harbor Legal Juniper a new aquarium-maintenance task; is there an existing owner? | (none) |
| legal:insufficient_metadata | development / insufficient_metadata / insufficient_metadata | Find the matter linked to sealed exhibit QX-LEGAL-73. | Juniper access terms |
| research:exact_name | development / exact_name / answerable | Lumen 文献レビュー 2026 | Lumen 文献レビュー 2026 |
| research:description | development / description / answerable | Who is repairing the absent bibliography entries in the Cedar Institute Lumen paper? | Lumen missing citations |
| research:paraphrase | development / paraphrase / answerable | For Cedar Institute Lumen, locate the person checking whether another lab can repeat our experiments. | Lumen reproducibility audit |
| research:same_entity | development / same_entity / answerable | Continue arranging participant interview times for Cedar Institute Lumen. | Lumen participant sessions |
| research:period_artifact | development / period_artifact / answerable | Find the Cedar Institute Lumen literature survey covering 2027 rather than 2026. | Lumen 文献レビュー 2027 |
| research:dormant | development / dormant / answerable | Locate Aiko Tanaka’s older Cedar Institute Lumen 2026 bibliography work. | Lumen 文献レビュー 2026 |
| research:multiple | development / multiple / answerable | Find both reference repair and participant scheduling for Cedar Institute Lumen. | Lumen missing citations; Lumen participant sessions |
| research:ambiguous | development / ambiguous / ambiguous | Who owns Cedar Institute Lumen literature-review updates? The year is unspecified. | Lumen 文献レビュー 2026; Lumen 文献レビュー 2027 |
| research:no_match | development / no_match / answerable | Start a new Cedar Institute Lumen fleet-insurance negotiation; is it already owned? | (none) |
| research:insufficient_metadata | development / insufficient_metadata / insufficient_metadata | Which worker has restricted notebook QX-RESEARCH-36? | Lumen reproducibility audit |
| events:exact_name | development / exact_name / answerable | Solstice venue renewal 2026 | Solstice venue renewal 2026 |
| events:description | development / description / answerable | Find the Aster Collective Solstice caterer-overbilling refund owner. | Solstice catering credit |
| events:paraphrase | development / paraphrase / answerable | Who checks that people can leave Aster Collective Solstice safely if an alarm sounds? | Solstice crowd safety |
| events:same_entity | development / same_entity / answerable | For Aster Collective Solstice, organize presenters arriving backstage rather than venue contracts. | Solstice speaker arrivals |
| events:period_artifact | development / period_artifact / answerable | Pick the Aster Collective Solstice hall agreement renewal for 2027. | Solstice venue renewal 2027 |
| events:dormant | development / dormant / answerable | Go back to Noah Williams’s old Aster Collective Solstice 2026 venue booking. | Solstice venue renewal 2026 |
| events:multiple | development / multiple / answerable | I need the catering-credit and speaker-arrival work for Aster Collective Solstice. | Solstice catering credit; Solstice speaker arrivals |
| events:ambiguous | development / ambiguous / ambiguous | Which workers manage Aster Collective Solstice venue renewals in either year? | Solstice venue renewal 2026; Solstice venue renewal 2027 |
| events:no_match | development / no_match / answerable | Create a new Aster Collective Solstice soil-analysis task; is it already assigned? | (none) |
| events:insufficient_metadata | development / insufficient_metadata / insufficient_metadata | Find the file owner for confidential voucher QX-EVENTS-29. | Solstice crowd safety |
| recruiting:exact_name | evaluation / exact_name / answerable | Kestrel hiring plan 2026 | Kestrel hiring plan 2026 |
| recruiting:description | evaluation / description / answerable | The Copper Finch Kestrel applicants are still owed their journey costs. Find that work. | Kestrel candidate expenses |
| recruiting:paraphrase | evaluation / paraphrase / answerable | Locate the Copper Finch Kestrel review of whether all applicants are being judged on the same basis. | Kestrel interview fairness |
| recruiting:same_entity | evaluation / same_entity / answerable | Who coordinates the interviewer diaries on Copper Finch Kestrel? | Kestrel panel calendars |
| recruiting:period_artifact | evaluation / period_artifact / answerable | I need the Copper Finch Kestrel staffing authorization for 2027, not last year’s plan. | Kestrel hiring plan 2027 |
| recruiting:dormant | evaluation / dormant / answerable | Find Priya Nair’s long-finished Copper Finch Kestrel 2026 headcount approval. | Kestrel hiring plan 2026 |
| recruiting:multiple | evaluation / multiple / answerable | Get both applicant travel repayments and panel scheduling for Copper Finch Kestrel. | Kestrel candidate expenses; Kestrel panel calendars |
| recruiting:ambiguous | evaluation / ambiguous / ambiguous | Bring up the Copper Finch Kestrel hiring-plan owners; I have not picked 2026 or 2027. | Kestrel hiring plan 2026; Kestrel hiring plan 2027 |
| recruiting:no_match | evaluation / no_match / answerable | Does anyone own a new Copper Finch Kestrel vineyard-irrigation redesign? | (none) |
| recruiting:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Identify the owner of private application token QX-RECRUITING-62. | Kestrel interview fairness |
| finance:exact_name | evaluation / exact_name / answerable | Estuary budget 2026 | Estuary budget 2026 |
| finance:description | evaluation / description / answerable | Find the Redwood Partners Estuary payment that never matched a ledger entry. | Estuary unmatched transfer |
| finance:paraphrase | evaluation / paraphrase / answerable | Who is checking that Redwood Partners Estuary spending is approved by the right people? | Estuary expense controls |
| finance:same_entity | evaluation / same_entity / answerable | For Redwood Partners Estuary, continue coordinating when the month-end reports are due. | Estuary close calendar |
| finance:period_artifact | evaluation / period_artifact / answerable | Use the Redwood Partners Estuary operating forecast for 2027 rather than 2026. | Estuary budget 2027 |
| finance:dormant | evaluation / dormant / answerable | Look up Luis Ortega’s old Redwood Partners Estuary 2026 budget preparation. | Estuary budget 2026 |
| finance:multiple | evaluation / multiple / answerable | I need the unmatched-transfer investigation plus the close timetable for Redwood Partners Estuary. | Estuary unmatched transfer; Estuary close calendar |
| finance:ambiguous | evaluation / ambiguous / ambiguous | Locate both Redwood Partners Estuary annual-budget owners without assuming the year. | Estuary budget 2026; Estuary budget 2027 |
| finance:no_match | evaluation / no_match / answerable | Who already handles a new Redwood Partners Estuary opera-costume fitting? | (none) |
| finance:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker linked to restricted ledger note QX-FINANCE-84. | Estuary expense controls |
| education:exact_name | evaluation / exact_name / answerable | Atlas curriculum 2026 | Atlas curriculum 2026 |
| education:description | evaluation / description / answerable | Which worker corrects the extra tuition paid for Oakridge College Atlas? | Atlas tuition adjustment |
| education:paraphrase | evaluation / paraphrase / answerable | Locate the Oakridge College Atlas work ensuring students with disabilities can take assessments. | Atlas assessment access |
| education:same_entity | evaluation / same_entity / answerable | Continue organizing tutor session times for Oakridge College Atlas. | Atlas tutorial timetable |
| education:period_artifact | evaluation / period_artifact / answerable | I want the Oakridge College Atlas syllabus renewal for the 2027 academic year. | Atlas curriculum 2027 |
| education:dormant | evaluation / dormant / answerable | Find Grace Okafor’s older Oakridge College Atlas 2026 course-outline work. | Atlas curriculum 2026 |
| education:multiple | evaluation / multiple / answerable | Bring back both tuition repayment and tutorial scheduling for Oakridge College Atlas. | Atlas tuition adjustment; Atlas tutorial timetable |
| education:ambiguous | evaluation / ambiguous / ambiguous | Show Oakridge College Atlas curriculum-renewal owners across the two academic years. | Atlas curriculum 2026; Atlas curriculum 2027 |
| education:no_match | evaluation / no_match / answerable | Start a new Oakridge College Atlas industrial-boiler inspection. Is it already owned? | (none) |
| education:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Who is responsible for private assessment record QX-EDUCATION-17? | Atlas assessment access |
| home:exact_name | evaluation / exact_name / answerable | Maple cover 2026 | Maple cover 2026 |
| home:description | evaluation / description / answerable | Who has the Willow Household Maple insurer’s response to the leak damage? | Maple water-damage claim |
| home:paraphrase | evaluation / paraphrase / answerable | Find the Willow Household Maple work checking whether the wiring is safe. | Maple electrical checks |
| home:same_entity | evaluation / same_entity / answerable | Get the Willow Household Maple tradesperson-access appointments, not the insurance work. | Maple contractor visits |
| home:period_artifact | evaluation / period_artifact / answerable | Continue Willow Household Maple home coverage for 2027 specifically. | Maple cover 2027 |
| home:dormant | evaluation / dormant / answerable | Retrieve Sofia Berg’s older Willow Household Maple 2026 property policy work. | Maple cover 2026 |
| home:multiple | evaluation / multiple / answerable | I need the water-damage claim and contractor-access schedule for Willow Household Maple. | Maple water-damage claim; Maple contractor visits |
| home:ambiguous | evaluation / ambiguous / ambiguous | Which workers renew Willow Household Maple home policies? The policy year is unclear. | Maple cover 2026; Maple cover 2027 |
| home:no_match | evaluation / no_match / answerable | Is there an owner for a new Willow Household Maple satellite-launch permit? | (none) |
| home:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Locate the owner of sealed household record QX-HOME-95. | Maple electrical checks |
| health_admin:exact_name | evaluation / exact_name / answerable | Birch equipment cover 2026 | Birch equipment cover 2026 |
| health_admin:description | evaluation / description / answerable | Find the Lakeside Clinic Birch work disputing a supplier charging us twice. | Birch duplicate supplier bill |
| health_admin:paraphrase | evaluation / paraphrase / answerable | Who is checking which staff may see Lakeside Clinic Birch administrative records? | Birch records access review |
| health_admin:same_entity | evaluation / same_entity / answerable | Continue booking the Lakeside Clinic Birch technician appointments. | Birch service visits |
| health_admin:period_artifact | evaluation / period_artifact / answerable | Take the Lakeside Clinic Birch equipment-service agreement for 2027 rather than 2026. | Birch equipment cover 2027 |
| health_admin:dormant | evaluation / dormant / answerable | Locate Daniel Kim’s long-inactive Lakeside Clinic Birch 2026 maintenance contract. | Birch equipment cover 2026 |
| health_admin:multiple | evaluation / multiple / answerable | Find both the duplicate-bill dispute and maintenance-visit calendar for Lakeside Clinic Birch. | Birch duplicate supplier bill; Birch service visits |
| health_admin:ambiguous | evaluation / ambiguous / ambiguous | Show the Lakeside Clinic Birch maintenance-agreement renewal owners for either year. | Birch equipment cover 2026; Birch equipment cover 2027 |
| health_admin:no_match | evaluation / no_match / answerable | Create Lakeside Clinic Birch’s first marine-freight charter task; is there an existing owner? | (none) |
| health_admin:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the owner of restricted administrative reference QX-HEALTH-43. | Birch records access review |
| opensource:exact_name | evaluation / exact_name / answerable | Quasar release support 2026 | Quasar release support 2026 |
| opensource:description | evaluation / description / answerable | Find the owner debugging Helix Foundation Quasar’s red integration pipeline. | Quasar broken build |
| opensource:paraphrase | evaluation / paraphrase / answerable | Who is checking whether Helix Foundation Quasar can legally redistribute its external packages? | Quasar dependency audit |
| opensource:same_entity | evaluation / same_entity / answerable | Continue organizing Helix Foundation Quasar maintainer shifts rather than investigating a build. | Quasar maintainer rota |
| opensource:period_artifact | evaluation / period_artifact / answerable | Choose Helix Foundation Quasar’s release-support renewal for 2027. | Quasar release support 2027 |
| opensource:dormant | evaluation / dormant / answerable | Find Mateo Silva’s old Helix Foundation Quasar 2026 support commitment. | Quasar release support 2026 |
| opensource:multiple | evaluation / multiple / answerable | I need the broken-build investigation and maintainer roster for Helix Foundation Quasar. | Quasar broken build; Quasar maintainer rota |
| opensource:ambiguous | evaluation / ambiguous / ambiguous | Which workers own Helix Foundation Quasar release-support renewals without a specified year? | Quasar release support 2026; Quasar release support 2027 |
| opensource:no_match | evaluation / no_match / answerable | Who already handles a new Helix Foundation Quasar livestock-vaccination schedule? | (none) |
| opensource:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker bound to embargoed artifact QX-OPENSOURCE-57. | Quasar dependency audit |
| procurement:exact_name | evaluation / exact_name / answerable | Orion supply terms 2026 | Orion supply terms 2026 |
| procurement:description | evaluation / description / answerable | Who is sorting out the Summit Works Orion equipment that arrived broken? | Orion damaged delivery |
| procurement:paraphrase | evaluation / paraphrase / answerable | Find the Summit Works Orion owner checking whether the vendor can stay in business. | Orion supplier diligence |
| procurement:same_entity | evaluation / same_entity / answerable | Continue arranging Summit Works Orion loading-bay appointments. | Orion receiving slots |
| procurement:period_artifact | evaluation / period_artifact / answerable | I mean Summit Works Orion’s equipment purchasing framework for 2027. | Orion supply terms 2027 |
| procurement:dormant | evaluation / dormant / answerable | Recover Hana Novak’s earlier Summit Works Orion 2026 supply-terms work. | Orion supply terms 2026 |
| procurement:multiple | evaluation / multiple / answerable | Bring back the damaged-delivery and warehouse-slot workers for Summit Works Orion. | Orion damaged delivery; Orion receiving slots |
| procurement:ambiguous | evaluation / ambiguous / ambiguous | Find Summit Works Orion equipment-supply renewal owners across the two years. | Orion supply terms 2026; Orion supply terms 2027 |
| procurement:no_match | evaluation / no_match / answerable | Is a new Summit Works Orion film-festival submission already owned? | (none) |
| procurement:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker for confidential purchase reference QX-PROCUREMENT-68. | Orion supplier diligence |
| logistics:exact_name | evaluation / exact_name / answerable | Vega freight agreement 2026 | Vega freight agreement 2026 |
| logistics:description | evaluation / description / answerable | Locate the Bluewater Cargo Vega consignment work about a pallet going missing. | Vega missing pallet |
| logistics:paraphrase | evaluation / paraphrase / answerable | Who is ensuring Bluewater Cargo Vega’s border-clearance paperwork is complete? | Vega customs documents |
| logistics:same_entity | evaluation / same_entity / answerable | Continue organizing the unloading crew for Bluewater Cargo Vega. | Vega dock roster |
| logistics:period_artifact | evaluation / period_artifact / answerable | Use Bluewater Cargo Vega’s carriage agreement renewal for 2027. | Vega freight agreement 2027 |
| logistics:dormant | evaluation / dormant / answerable | Look up Amira Saleh’s dormant Bluewater Cargo Vega 2026 freight-contract work. | Vega freight agreement 2026 |
| logistics:multiple | evaluation / multiple / answerable | I need the missing-pallet investigation and dock staffing for Bluewater Cargo Vega. | Vega missing pallet; Vega dock roster |
| logistics:ambiguous | evaluation / ambiguous / ambiguous | Find the Bluewater Cargo Vega freight-contract owners; the year has not been supplied. | Vega freight agreement 2026; Vega freight agreement 2027 |
| logistics:no_match | evaluation / no_match / answerable | Is anyone assigned a new Bluewater Cargo Vega choir-audition program? | (none) |
| logistics:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker associated with sealed manifest QX-LOGISTICS-24. | Vega customs documents |
| design:exact_name | evaluation / exact_name / answerable | Prism design retainer 2026 | Prism design retainer 2026 |
| design:description | evaluation / description / answerable | Find the Marigold Studio Prism argument about an extra iteration charge. | Prism disputed revision fee |
| design:paraphrase | evaluation / paraphrase / answerable | Who checks whether Marigold Studio Prism screens remain readable for people with low vision? | Prism contrast review |
| design:same_entity | evaluation / same_entity / answerable | Continue arranging Marigold Studio Prism usability-test appointments. | Prism research bookings |
| design:period_artifact | evaluation / period_artifact / answerable | Pick the Marigold Studio Prism creative-services retainer for 2027. | Prism design retainer 2027 |
| design:dormant | evaluation / dormant / answerable | Find Camille Dubois’s old Marigold Studio Prism 2026 retainer work. | Prism design retainer 2026 |
| design:multiple | evaluation / multiple / answerable | Get both the revision-fee dispute and user-study scheduling for Marigold Studio Prism. | Prism disputed revision fee; Prism research bookings |
| design:ambiguous | evaluation / ambiguous / ambiguous | Show Marigold Studio Prism design-retainer renewal owners without assuming the year. | Prism design retainer 2026; Prism design retainer 2027 |
| design:no_match | evaluation / no_match / answerable | Start a new Marigold Studio Prism archaeological excavation task; is there an owner? | (none) |
| design:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker linked to private mockup QX-DESIGN-39. | Prism contrast review |
| nonprofit:exact_name | evaluation / exact_name / answerable | Tern grant renewal 2026 | Tern grant renewal 2026 |
| nonprofit:description | evaluation / description / answerable | Who is tracing the Riverton Aid Tern contribution that was never acknowledged? | Tern missing donation |
| nonprofit:paraphrase | evaluation / paraphrase / answerable | Find the Riverton Aid Tern owner checking how volunteers protect vulnerable participants. | Tern safeguarding review |
| nonprofit:same_entity | evaluation / same_entity / answerable | Continue arranging Riverton Aid Tern volunteer coverage on distribution days. | Tern volunteer shifts |
| nonprofit:period_artifact | evaluation / period_artifact / answerable | I want Riverton Aid Tern’s community-funding renewal for 2027. | Tern grant renewal 2027 |
| nonprofit:dormant | evaluation / dormant / answerable | Locate Kwame Mensah’s completed Riverton Aid Tern 2026 grant application work. | Tern grant renewal 2026 |
| nonprofit:multiple | evaluation / multiple / answerable | Get the uncredited-donation and volunteer-shift workers for Riverton Aid Tern. | Tern missing donation; Tern volunteer shifts |
| nonprofit:ambiguous | evaluation / ambiguous / ambiguous | Find the Riverton Aid Tern annual-grant owners for either funding year. | Tern grant renewal 2026; Tern grant renewal 2027 |
| nonprofit:no_match | evaluation / no_match / answerable | Is there an existing owner for a new Riverton Aid Tern semiconductor-fabrication review? | (none) |
| nonprofit:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the owner of confidential donor receipt QX-NONPROFIT-76. | Tern safeguarding review |
| property:exact_name | evaluation / exact_name / answerable | Spruce service contract 2026 | Spruce service contract 2026 |
| property:description | evaluation / description / answerable | Find the Elmstone Estates Spruce tenant bill that was apportioned incorrectly. | Spruce incorrect service charge |
| property:paraphrase | evaluation / paraphrase / answerable | Who is checking whether Elmstone Estates Spruce’s corridor doors meet fire rules? | Spruce fire-door review |
| property:same_entity | evaluation / same_entity / answerable | Continue arranging resident inspection appointments at Elmstone Estates Spruce. | Spruce resident visits |
| property:period_artifact | evaluation / period_artifact / answerable | Find Elmstone Estates Spruce’s facilities-service renewal for 2027. | Spruce service contract 2027 |
| property:dormant | evaluation / dormant / answerable | Look up Isabel Costa’s older Elmstone Estates Spruce 2026 building-services agreement. | Spruce service contract 2026 |
| property:multiple | evaluation / multiple / answerable | I need the tenant-charge correction and resident-visit schedule for Elmstone Estates Spruce. | Spruce incorrect service charge; Spruce resident visits |
| property:ambiguous | evaluation / ambiguous / ambiguous | Show both Elmstone Estates Spruce building-service renewal owners, with the year unresolved. | Spruce service contract 2026; Spruce service contract 2027 |
| property:no_match | evaluation / no_match / answerable | Does anyone own a new Elmstone Estates Spruce ballet-tour itinerary? | (none) |
| property:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker for sealed tenancy document QX-PROPERTY-81. | Spruce fire-door review |
| manufacturing:exact_name | evaluation / exact_name / answerable | Cobalt calibration contract 2026 | Cobalt calibration contract 2026 |
| manufacturing:description | evaluation / description / answerable | Locate the Ironwood Tools Cobalt work tracing why a production lot failed acceptance. | Cobalt rejected batch |
| manufacturing:paraphrase | evaluation / paraphrase / answerable | Who is checking that Ironwood Tools Cobalt operators cannot reach moving machinery? | Cobalt machine guarding |
| manufacturing:same_entity | evaluation / same_entity / answerable | Continue coordinating Ironwood Tools Cobalt’s planned downtime. | Cobalt shutdown calendar |
| manufacturing:period_artifact | evaluation / period_artifact / answerable | Pick Ironwood Tools Cobalt’s calibration-service contract for 2027. | Cobalt calibration contract 2027 |
| manufacturing:dormant | evaluation / dormant / answerable | Retrieve Tomasz Zielinski’s long-finished Ironwood Tools Cobalt 2026 calibration agreement. | Cobalt calibration contract 2026 |
| manufacturing:multiple | evaluation / multiple / answerable | Find both rejected-batch analysis and shutdown scheduling for Ironwood Tools Cobalt. | Cobalt rejected batch; Cobalt shutdown calendar |
| manufacturing:ambiguous | evaluation / ambiguous / ambiguous | Which workers own Ironwood Tools Cobalt calibration renewals, without a year? | Cobalt calibration contract 2026; Cobalt calibration contract 2027 |
| manufacturing:no_match | evaluation / no_match / answerable | Is a new Ironwood Tools Cobalt coral-restoration project already assigned? | (none) |
| manufacturing:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker linked to restricted lot certificate QX-MANUFACTURING-92. | Cobalt machine guarding |
| agriculture:exact_name | evaluation / exact_name / answerable | Saffron water allocation 2026 | Saffron water allocation 2026 |
| agriculture:description | evaluation / description / answerable | Find the Meadowlark Farm Saffron supplier claim about missing seed bags. | Saffron seed delivery claim |
| agriculture:paraphrase | evaluation / paraphrase / answerable | Who checks Meadowlark Farm Saffron’s earth-sample evidence for organic approval? | Saffron soil certification |
| agriculture:same_entity | evaluation / same_entity / answerable | Continue arranging pickers for Meadowlark Farm Saffron harvest days. | Saffron harvest crews |
| agriculture:period_artifact | evaluation / period_artifact / answerable | I want Meadowlark Farm Saffron’s irrigation entitlement for 2027. | Saffron water allocation 2027 |
| agriculture:dormant | evaluation / dormant / answerable | Find Nadia Rahman’s older Meadowlark Farm Saffron 2026 water-allocation application. | Saffron water allocation 2026 |
| agriculture:multiple | evaluation / multiple / answerable | Get the seed-shortage claim and harvest-crew schedule for Meadowlark Farm Saffron. | Saffron seed delivery claim; Saffron harvest crews |
| agriculture:ambiguous | evaluation / ambiguous / ambiguous | Show the Meadowlark Farm Saffron water-allocation renewal owners across both years. | Saffron water allocation 2026; Saffron water allocation 2027 |
| agriculture:no_match | evaluation / no_match / answerable | Does anyone own a new Meadowlark Farm Saffron mobile-app penetration test? | (none) |
| agriculture:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker associated with sealed field note QX-AGRICULTURE-65. | Saffron soil certification |
| publishing:exact_name | evaluation / exact_name / answerable | Horizon rights 2026 | Horizon rights 2026 |
| publishing:description | evaluation / description / answerable | Who is correcting the Paperkite Press Horizon author-payment statement? | Horizon royalty correction |
| publishing:paraphrase | evaluation / paraphrase / answerable | Find the Paperkite Press Horizon owner checking whether the artwork can be reproduced. | Horizon permissions audit |
| publishing:same_entity | evaluation / same_entity / answerable | Continue arranging Paperkite Press Horizon page-proof deadlines. | Horizon proof timetable |
| publishing:period_artifact | evaluation / period_artifact / answerable | Choose Paperkite Press Horizon’s translation-rights renewal for 2027. | Horizon rights 2027 |
| publishing:dormant | evaluation / dormant / answerable | Locate Lea Muller’s old Paperkite Press Horizon 2026 foreign-language rights agreement. | Horizon rights 2026 |
| publishing:multiple | evaluation / multiple / answerable | I need royalty reconciliation and proof scheduling for Paperkite Press Horizon. | Horizon royalty correction; Horizon proof timetable |
| publishing:ambiguous | evaluation / ambiguous / ambiguous | Which workers handle Paperkite Press Horizon translation-rights renewals, with no year supplied? | Horizon rights 2026; Horizon rights 2027 |
| publishing:no_match | evaluation / no_match / answerable | Start a new Paperkite Press Horizon turbine-overhaul task; is there an owner? | (none) |
| publishing:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker for confidential manuscript reference QX-PUBLISHING-28. | Horizon permissions audit |
| security:exact_name | evaluation / exact_name / answerable | Nimbus monitoring contract 2026 | Nimbus monitoring contract 2026 |
| security:description | evaluation / description / answerable | Find the Stonebridge Systems Nimbus investigation into unusual login attempts. | Nimbus suspicious sign-in |
| security:paraphrase | evaluation / paraphrase / answerable | Who checks that Stonebridge Systems Nimbus can be recovered from saved copies after a failure? | Nimbus restore exercise |
| security:same_entity | evaluation / same_entity / answerable | Continue organizing Stonebridge Systems Nimbus responder shifts. | Nimbus on-call coverage |
| security:period_artifact | evaluation / period_artifact / answerable | I mean Stonebridge Systems Nimbus’s monitoring-service renewal for 2027. | Nimbus monitoring contract 2027 |
| security:dormant | evaluation / dormant / answerable | Find Yuki Sato’s dormant Stonebridge Systems Nimbus 2026 monitoring contract. | Nimbus monitoring contract 2026 |
| security:multiple | evaluation / multiple / answerable | Get both the suspicious-login investigation and on-call rota for Stonebridge Systems Nimbus. | Nimbus suspicious sign-in; Nimbus on-call coverage |
| security:ambiguous | evaluation / ambiguous / ambiguous | Show Stonebridge Systems Nimbus monitoring-renewal owners for the unspecified year. | Nimbus monitoring contract 2026; Nimbus monitoring contract 2027 |
| security:no_match | evaluation / no_match / answerable | Is anyone assigned a new Stonebridge Systems Nimbus orchard-pruning schedule? | (none) |
| security:insufficient_metadata | evaluation / insufficient_metadata / insufficient_metadata | Find the worker attached to embargoed incident token QX-SECURITY-46. | Nimbus restore exercise |

The original raw result rows and complete frozen catalog snapshots are retained under [20261113T055958Z-full-suite](D:/personal_projects/openpoke/evals/agent_overload/runs/20261113T055958Z-full-suite). This report copies the numeric summaries and provenance; original per-run artifact manifests refer to those complete raw run directories.
