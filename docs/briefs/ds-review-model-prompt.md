# Optional model prompt: read one datasheet excerpt (provider-neutral)

Use with any vision model you run yourself. `tools/ds_review.py` makes no model calls. The answer is a second opinion
for the human: it never changes `component.toml`, a `verified` stamp, a review status or a ledger state.

Inputs per Param: the image `.review-cache/<Mfr>/<Value>/evidence/<image>.png`, its page link `<datasheet_url>#page=<n>`,
and the parameter name and symbol from `.review-cache/<Mfr>/<Value>/params/<key>.md`. Do not show the model the committed values.

Prompt:

> You are reading one excerpt of a component datasheet. Find the row for the parameter named below and transcribe
> only what is visible in the image. Rules: quote text exactly as printed, including signs, ± signs, units and
> footnote markers; never infer, convert, round or fill a missing value; keep what you see separate from what you
> interpret; if the row, a column heading or a value is unclear, cut off or ambiguous, set "abstain": true and say
> why. Answer with JSON only, in exactly this shape:
>
> ```json
> {"param": "<key>",
>  "visible_quote": "<the row's text as printed>",
>  "column_headings": ["<as printed>"],
>  "units": "<as printed or empty>",
>  "conditions": "<as printed or empty>",
>  "footnotes": ["<marker: text, as printed>"],
>  "values": {"min": "<as printed or null>", "typ": "<as printed or null>", "max": "<as printed or null>"},
>  "interpretation": "<optional: which column a value sits in when the layout is unusual>",
>  "abstain": false,
>  "reason": "<why abstained, or empty>"}
> ```
>
> Parameter: <name> (<symbol>). Page link: <datasheet_url>#page=<n>.

Use: a person compares the JSON with the committed TOML and the image. A mismatch is a question to check on the page,
never a value to copy. An abstention means a person reads the page.
