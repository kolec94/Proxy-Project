# Residential Proxy Business 30 Day Pilot Plan

Windows paid acquisition • Own SDK and proxy network • Prepared September 26 2026

## Purpose and success criteria

Use a maximum of $100 to test whether paid Windows installs can produce consenting residential endpoints that paying customers actually use. Start with one geography, one acquisition source, and a small authenticated customer pilot. Keep Android TV and Android phones for later comparison.

The month should produce a working client and gateway, a measured acquisition cohort, customer usage evidence, and a stop or continue decision. A profitable month is not promised. All financial assumptions below are planning inputs until replaced with measured results.

## Budget and cash controls

| Allocation | Cap | Release condition |
| --- | --- | --- |
| Acquisition batch A | $35 | Client validated and buyer trial agreed |
| Acquisition batch B | $35 | Batch A passes the day 7 review |
| Gateway and operating costs | $20 | Metered plan with a spending cap |
| Contingency | $10 | Required pilot cost only |
| Total maximum outlay | $100 | No automatic top ups or renewals |

Use an existing development machine and a free landing page or existing domain. Reserve covers gateway charges, necessary fees, and testing; unused money stays unspent. Track provider egress separately from customer billable bytes. Do not assume a $20 hosting allowance includes enough transfer.

### Conditions for the budget to work

Development labor, existing equipment, business formation, legal review, and a new code-signing certificate are outside this $100 experiment. Do not purchase hardware. If a required signing, distribution, hosting, or acquisition minimum exceeds the reserve, pause paid acquisition and revise scope; do not ask users to disable security protections.

Day 1 is the chosen kickoff date. The owner performs development, supplier evaluation, customer discovery, and the daily review. SDK readiness determines whether paid installs can begin within this month.

## Days 1 through 7

### Days 1 and 2   Define the offer and verify demand

Choose Windows home broadband in one country that a prospective buyer actually needs. Define price per GB, intended workloads, concurrency, session expectations, transfer limits, and refund terms. Limit the first customer to a known, reviewed public-web use case.

Identify 5 to 10 prospective buyers and seek one small paid trial, with written usage and payment terms. Record a buyer’s requested geography, expected GB, acceptable success rate, and willingness to pay. A free trial or your own test traffic validates operation but is not sales revenue.

### Days 2 and 3   Obtain install quotes

Request written quotes from at least two acquisition sources. Ask for Windows desktop delivery, geography and ISP mix, disclosure shown before installation, opt-in attribution, incentivized versus organic traffic, minimum deposit, refund rules, and 7-day retention reporting. Verify that the source accepts this disclosed proxy use case.

Use separate source identifiers. No hidden bundles, forced installations, or payment for fabricated traffic. Reject a source that cannot explain how users agree to third-party traffic routing. A supplier with a minimum above $35 is outside the first-batch budget unless it offers a smaller pilot.

### Days 3 through 6   Finish the minimum product

Client: explicit consent before sharing, visible status, start and pause controls, bandwidth cap, automatic-update integrity, easy uninstall, and consent withdrawal. Use a small Windows client around the SDK. Respect sleep and user controls.

Backend: authenticated customer gateway, authenticated encrypted outbound device connections, device revocation, per-customer quotas, session routing, metering, and a global stop control. Keep billing credentials on the backend. Block access to local, private, link-local, and metadata addresses, including after DNS resolution changes.

Operations: limit destination ports and destinations to the pilot’s agreed needs; block unsolicited email traffic. Maintain an abuse contact and minimal operational records with a defined deletion period. Do not log credentials or page bodies. Review traffic complaints promptly and suspend the affected customer.

### Day 7   Technical release decision

Test on 3 to 5 authorized devices: install, opt-in, pause, uninstall, network change, restart, sleep, connection loss, quotas, and gateway rejection of forbidden destinations. Confirm withdrawal stops routing and revocation works. Compare client, gateway, and customer byte counts; document billing units and any differences.

If the client is incomplete, no buyer trial is agreed, or no suitable install source is available, keep the $70 acquisition budget unspent. Continue development and discovery; the calendar is not a reason to buy unusable installs.

## Days 8 through 30

### Days 8 through 10   Launch batch A

Release up to $35 to one accepted source. At a hypothetical $1 CPI this buys about 35 installs. Use the same country and client build across the cohort. Record installation date, source, disclosure version, opt-in, qualified activity, and attributed cost.

Activate only a small number of reviewed customer sessions. Start with tight quotas and monitor successful requests, traffic costs, and user impact. Keep test traffic tagged separately from customer traffic.

### Days 11 through 17   Review quality before buying more

Review metrics daily and investigate connection failures, duplicate exits, unexpected data use, complaints, and cost spikes. At seven days after each install, calculate retention only for users old enough to be measured.

Release batch B only if: at least 20 installs have enough observation time; opt-in is at least 50%; at least 60% of opt-ins remain usable at day 7; at least 90% of controlled requests to agreed test destinations succeed; measured variable contribution is positive; and no unresolved consent or serious security issue remains. These are pilot decision rules, not industry benchmarks.

If the sample is too small, observe longer without buying more. If request failures are caused by your gateway or client, repair the product before blaming retention or replacing the supplier.

### Days 18 through 20   Optional batch B

Spend up to $35 only after the review passes. Prefer repeating the same source and targeting so results remain comparable. Do not split a tiny budget across three operating systems. Document any change to creative, reward, version, or targeting.

### Days 21 through 27   Validate actual economics

Run the agreed customer trial, reconcile billable usage and costs, and collect payment according to terms. Record money received separately from invoices or prepaid balances. Reserve enough to fulfill any remaining prepaid service or refunds.

Check endpoint availability across different hours, repeat requests, and sleep cycles. Ask participating users about performance and clarity of controls. Do not manufacture traffic to make revenue or utilization appear higher.

### Days 28 through 30   Make the business review

Produce the [review record below](#day-30-review-record). Decide whether to stop, repair and observe, or continue at the same small scale. Confirm a repeat buyer before expanding acquisition. Record all unpaid bills and committed costs.

Day 30 of the plan is not day-30 cohort retention. Installs acquired on days 8 to 10 reach age 30 around plan days 38 to 40; batch B reaches it around days 48 to 50. Schedule those reviews before treating long-term retention or six-month profit as validated.

## Financial model and measurement

Use the following Windows baseline only to set hypotheses. It assumes the app and customer demand are ready; it does not forecast the first month’s cash receipts.

| Input | Planning value | Meaning |
| --- | --- | --- |
| Cost per install | $1.00 | Unverified supplier price |
| Opt-in rate | 60% | Of attributed paid installs |
| Day 30 retention | 60% | Of opted-in devices, still eligible and usable |
| Acquisition cost per retained device | $2.78 | $1 divided by 0.60 divided by 0.60 |
| Billable traffic | 2 GB per month | Per retained endpoint; buyer demand required |
| Realized selling price | $0.75 per GB | Actual revenue after discounts |
| Variable cost allowance | $0.25 per GB | Replace with egress, fees, rewards and direct costs |
| Monthly contribution | $1.00 per endpoint | 2 GB multiplied by $0.50 margin |
| Monthly loss after day 30 | 10% | Unverified cohort attrition assumption |

### What the baseline implies

$70 at $1 CPI produces 70 installs and an expected 25.2 usable day-30 devices. If all those assumptions hold, the following six earning months produce $118.08 contribution after variable costs and modeled churn. Subtract $70 acquisition and a fully spent $30 reserve: $18.08 remains before labor, tax, and additional overhead. This is a post-day-30 scenario, not a 30-day result.

At only 1 billable GB per endpoint-month, that six-month contribution falls to $59.04 and the result after the same $100 outlay becomes a $40.96 loss. At zero paying demand, revenue is zero. Higher retention alone cannot create customers.

### Metrics to record every day

Record spend, installs, opt-ins, qualified endpoint-hours, current unique residential IPs, eligible cohort sizes, customer billable GB, gateway transfer, success rate, realized revenue, cash collected, variable costs, fixed costs, complaints, and outstanding obligations.

Define a usable device as consented, reachable, residential in the chosen geography, and able to complete an authorized test. Report both device retention and unique-IP availability; IP changes and shared households can distort counts.

Calculate retention using same-age cohorts. Calculate contribution as earned customer revenue minus variable costs. Calculate operating result after acquisition and fixed costs. Calculate spendable cash separately; unearned prepayments are not profit.

## Decision rules and reinvestment

| Decision | Evidence | Action |
| --- | --- | --- |
| Stop acquisition | Consent failure, serious unresolved security issue, or uncontrolled costs | Disable affected routing and freeze spending until resolved |
| Repair and observe | Poor day 7 results, no paid demand, or insufficient cohort age | Keep reserve; fix the issue and extend observation |
| Continue small pilot | Quality gates pass and real customer traffic has positive contribution | Observe mature retention and seek repeat business |
| Expand later | Age 30 cohort measured, repeat paying demand, costs reconciled | Reinvest only eligible collected profit |

### Reinvestment policy

After paying costs and reserving taxes, refunds, participant amounts owed, and future service obligations, allocate up to 70% of remaining collected profit to acquisition. Keep at least 30% as a cash buffer. If there is no eligible profit, reinvest $0.

Do not assume installs scale at the original CPI or that additional supply receives the same demand. Increase one small batch at a time. Before expanding, require modeled six-month contribution per install to be at least twice CPI, using measured usage and a conservative churn assumption. This is a chosen safety margin, not a market standard.

The baseline six-month contribution per install is about $1.69, so it does not meet that 2x rule at $1 CPI. It would need CPI of about $0.84 or lower, or better measured contribution and retention. Extend observation rather than declaring success from the optimistic scenario.

### Day 30 review record

Actual spend: ______   Cash received: ______   Outstanding costs: ______

Installs: ______   Opt-ins: ______   Mature day 7 cohort size: ______

Day 7 usable retention: ______   Paid GB: ______   Variable contribution: ______

Repeat buyer evidence: ______   Oldest cohort age: ______

Decision and reason: __________________________________________________

Next cohort review dates: ______________________________________________

### Sources and evidence boundaries

Reviewed September 26 2026. Technical support and market context below do not validate the model’s CPI, retention, usage, or selling price.

Microsoft describes Windows services for long-running background workloads. https://learn.microsoft.com/en-us/windows/win32/services/about-services

AppBrain publishes Android CPI bids by country; these are not Windows or proxy-client quotes. https://www.appbrain.com/stats/android-cpi-per-country

Google Play requires third-party proxy service to be the primary user-facing app purpose; relevant to a later Android test. https://support.google.com/googleplay/android-developer/answer/16559646?hl=en
