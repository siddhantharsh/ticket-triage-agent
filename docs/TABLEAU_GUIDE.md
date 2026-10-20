# Tableau Public guide: triage dashboard

Build one dashboard from `data/triage_results.csv` using Tableau Public web authoring.
It is free, runs in a browser (fine on Linux) and needs no install. Plan on about
90 minutes the first time.

**Reminder:** the data is synthetic output from the mock-mode pipeline. Say so on the
dashboard itself (step 9) and in anything you publish. Do not describe it as real
customer data or as real model performance.

Tableau updates its web UI now and then, so a menu label may differ slightly from
what is written here. The ideas (drag a field to Columns, Rows, Color, Text) stay the same.

## Vocabulary in 60 seconds

- **Dimension**: a category field (blue pill), for example `severity`. Splits the view.
- **Measure**: a number field (green pill), for example `confidence`. Gets aggregated (SUM, AVG, COUNT).
- **Columns / Rows shelves**: the top and left of the canvas. Dragging a field there draws an axis.
- **Marks card**: the box with Color, Size, Label (Text). Dragging a field onto Color, Label and so on styles the chart.
- **Worksheet**: one chart. **Dashboard**: a canvas where you arrange several worksheets.

## 1. Account and data (10 min)

1. Go to https://public.tableau.com and create a free account (or sign in).
2. Click **Create**, then **Web Authoring** (it may also be labelled **New workbook**).
3. When asked to connect to data, choose **Upload from computer** and pick `data/triage_results.csv`.
4. On the data source page, check the field types. Click the small icon left of each field name to change it:
   - `created_date`: **Date** (not Date & Time, not String)
   - `confidence`, `latency_ms`: **Number (decimal)**
   - everything else: **String**
5. Click **New Worksheet** (or the sheet tab at the bottom).

Rename sheets as you go (double-click the tab). The names below are used in the dashboard step.

## 2. Calculated fields (10 min)

Open **Data pane > drop-down arrow next to the search box > Create Calculated Field**
(in some versions: **Analysis > Create Calculated Field**). Make these five. Names matter,
because later steps refer to them. Quotes must be straight quotes (type them, do not paste from a word processor).

| Name | Formula |
| --- | --- |
| `Total Tickets` | `COUNTD([ticket_id])` |
| `Auto-Resolve Rate` | `SUM(IF [decision]='auto_resolved' THEN 1 ELSE 0 END)/COUNT([ticket_id])` |
| `Escalation Rate` | `SUM(IF [decision]='escalated' THEN 1 ELSE 0 END)/COUNT([ticket_id])` |
| `Avg Confidence` | `AVG([confidence])` |
| `Confidence Bucket` | `FLOOR([confidence]/0.05)*0.05` |

Sanity check: Auto-Resolve Rate plus Escalation Rate must equal 100%.

## 3. KPI tiles (4 sheets, 15 min)

Repeat for each of `Total Tickets`, `Auto-Resolve Rate`, `Escalation Rate`, `Avg Confidence`.
Use one new worksheet per tile and name it `KPI Total`, `KPI Auto`, `KPI Escalated`, `KPI Confidence`.

1. Drag the calculated field onto **Text** on the Marks card (or double-click it; Tableau puts it on the canvas as text).
2. Right-click the pill on Marks, **Format**, then set the number format:
   - Total Tickets: Number, 0 decimals
   - the two rates: **Percentage**, 1 decimal
   - Avg Confidence: Number, 2 decimals
3. Click **Text** on the Marks card, then the `...` button. Make the number big (28 to 36 pt, bold). Add a line above it as a title, for example "Auto-resolve rate", in a small grey font.
4. Hide the sheet title if you like (right-click the title, **Hide Title**) and set the view to **Entire View** in the toolbar drop-down.

## 4. Severity distribution (bar chart, 5 min)

Sheet name: `Severity`.

1. Drag `severity` to **Columns**.
2. Drag `Total Tickets` to **Rows**.
3. Order the bars logically: right-click `severity` in the view, **Sort**, **Manual**, then arrange `low`, `medium`, `high`.
4. Drag `severity` to **Color** and assign green (low), amber (medium), red (high) via **Color > Edit Colors**.
5. Drag `Total Tickets` to **Label** (or click the **T** icon in the toolbar) to show counts on bars.

## 5. Category by severity (stacked bar, 10 min)

Sheet name: `Category x Severity`.

1. Drag `category` to **Columns**.
2. Drag `Total Tickets` to **Rows**.
3. Drag `severity` to **Color**. Bars stack automatically. Reuse the colours from step 4.
4. Optionally sort categories by size: click the sort icon that appears when you hover the axis label.
5. Show counts: drag `Total Tickets` to **Label**.

## 6. Confidence histogram (10 min)

Sheet name: `Confidence`.

1. Right-click `Confidence Bucket` in the Data pane, **Convert to Discrete** (or drag it to Columns and click its drop-down, **Discrete**).
2. Drag `Confidence Bucket` to **Columns**.
3. Drag `Total Tickets` to **Rows**.
4. Right-click the axis header, **Edit Axis**, and set the title to `Confidence (bucket start, width 0.05)`.
5. Optional: drag `decision` to **Color** to see which buckets are escalated.

Why a calculated field and not Show Me > Histogram? It works the same in every Tableau edition and you control the width.

## 7. Tickets per day (line chart, 8 min)

Sheet name: `Tickets per Day`.

1. Drag `created_date` to **Columns**. Click its drop-down and choose **Day** from the continuous (green) group, the second "Day" section in the menu, the one that shows a full date.
2. Drag `Total Tickets` to **Rows**. The mark type should be **Line** (change it in the Marks card drop-down if it is not).
3. Optional: right-click the axis, **Add Reference Line**, set it to **Average**.

## 8. Top escalation reasons (bar chart, 8 min)

Sheet name: `Escalation Reasons`.

1. Drag `decision` to **Filters**, tick only `escalated`, **OK**. This removes the `none` reason that auto-resolved tickets carry.
2. Drag `escalation_reason` to **Rows**.
3. Drag `Total Tickets` to **Columns**.
4. Sort descending with the sort icon in the toolbar (the bar with a downward arrow).
5. Label the bars with `Total Tickets`. In this dataset the only reasons are `high_severity` and `low_confidence`, so "top" is a two-bar ranking.

## 9. Assemble the dashboard (20 min)

1. Click the **New Dashboard** icon (next to the new worksheet tab). Rename it `Ticket Triage Overview`.
2. Bottom-left, set **Size** to **Fixed size** with `1200 x 800` (or Automatic if you prefer a fluid layout).
3. Layout, top to bottom (drag worksheets from the left list onto the canvas; the blue drop zone shows where it will land):

```
+--------------------------------------------------------------+
| Title: Support Ticket Triage (synthetic mock-mode data)      |
+------------+--------------+--------------+-------------------+
| KPI Total  | KPI Auto     | KPI Escalated| KPI Confidence    |
+------------+--------------+--------------+-------------------+
| Severity                  | Category x Severity              |
+---------------------------+----------------------------------+
| Confidence                | Escalation Reasons               |
+---------------------------+----------------------------------+
| Tickets per Day                                              |
+--------------------------------------------------------------+
```

4. Build it with containers: drag a **Horizontal** container (from the Objects list) to the top and drop the four KPI sheets into it. Use another horizontal container for each two-chart row, and put the line chart alone at the bottom.
5. Drag a **Text** object to the very top and type: `Support Ticket Triage (synthetic mock-mode data, not real customers)`.
6. Add a **Text** object at the bottom: `Source: data/triage_results.csv, generated by scripts/generate_demo_tickets.py with MOCK_BEDROCK=true.`
7. Tidy up:
   - Select each worksheet in the dashboard, click the drop-down arrow, **Fit > Entire View**.
   - Remove duplicate legends. Keep one severity legend (a worksheet's drop-down arrow, **Legends**, then tick it).
   - Turn off chart titles that repeat what the axis already says; keep short titles for the charts.
   - Use **Layout** tab padding of 8 to 10 px and one font family throughout.
8. Optional interactivity: on a chart, click the **Use as Filter** funnel icon, for example on `Severity`, so clicking a bar filters the rest.

## 10. Publish and copy the public link (5 min)

1. Click **Publish As...** (or **Save** in web authoring, which saves to Tableau Public) and give it a name such as `Support Ticket Triage (synthetic data)`.
2. Wait for the confirmation, then open the published view in the browser.
3. Copy the URL from the address bar. It looks like `https://public.tableau.com/app/profile/<your-name>/viz/<workbook>/<dashboard>`.
4. Optional: use the **Share** button at the bottom of the viz for the embed or link options.
5. Paste the link into the README under "Analytics dashboard", replacing the TODO.
6. Take a screenshot of the dashboard, save it as `docs/dashboard.png`, and uncomment the image line in the README.

Anything you publish to Tableau Public is visible to everyone, which is fine here because the data is fake. Never upload real customer data to Tableau Public.

## Troubleshooting

- **`created_date` shows as text or the line chart is a single point**: fix the field type on the data source page (step 1.4) and use the continuous Day option.
- **Calculated field is red or shows an error**: check straight quotes and that field names match the CSV exactly (`decision`, `ticket_id`, `confidence`).
- **Percentages show as 0.35 rather than 35%**: right-click the pill, **Format**, set the number to Percentage.
- **Severity bars are in alphabetical order**: redo the manual sort in step 4.
- **Want fresh data**: regenerate the CSV (see README), then in web authoring use **Data > Replace Data Source** or re-upload the file. Column names must stay the same.
