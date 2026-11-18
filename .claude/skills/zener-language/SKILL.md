---
name: zener-language
description: Read or edit Zener HDL, package APIs, and tool-managed dependencies.
---

# Zener Language

Zener is Starlark plus PCB-specific modules, typed electrical connections, physical parts, sourcing, layout, and diagnostics.

## Discover Before Authoring

Use `pcb list -m -json @stdlib` or `pcb list -m -json <package>[@<version>]` to find a package's local source directory, then read its `.zen` files for the public API and exact behavior. For CLI behavior use the installed command's `--help`; do not invent subcommands or flags. When version history matters, check the installed version against the [`pcb` changelog](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md).

## Modules and Components

A `.zen` file is a normal module imported with `load()` or an instantiable schematic module imported with `Module()`. Relative paths stay within the current package; cross-package imports use full package URLs:

```zen
load("./helpers.zen", "helper")
LocalBlock = Module("./LocalBlock.zen")
RemoteBlock = Module("github.com/org/repo/modules/RemoteBlock.zen")
```

An instantiation passes `name=...`, its public `io()` and `config()` inputs, and optional `dnp` and `properties`. `name` is instance-path identity, not a fixed reference designator; use refdes-like names only when the user asks (then set `prefix=` on the `Component()`).

`Component()` creates a physical part from `name`, `symbol`, and `pins`. The symbol is the authority for footprint, part identity, datasheet and pins: keep those correct in `.kicad_sym`, not in Zener. Omit true `no_connect` pins (auto `NotConnected()`). Use `Symbol(library, name=...)` for multi-symbol libraries and `Part(mpn=..., manufacturer=...)` only when the symbol lacks part identity.

`Project()` takes `layout = False` or `schematic = False`. Use one declaration per entrypoint with a config-independent path relative to its `.zen` file.

## IO and Config

Define public electrical connections as flat top-level assignments (no legacy `Pins = struct(...)`):

```zen
VDD = io(Power(voltage="3.0V to 5.5V"))
GND = io(Ground)
EN = io(Net, optional=True)
```

With `optional=True`, an omitted IO gets an automatically generated net. `Net` is the base type; `Power`, `Ground`, `NotConnected` and stdlib interfaces add semantics. Across an `io()` boundary `NotConnected` promotes to any net type, a specialized net demotes to `Net`, and a plain `Net` does not gain semantics: adapt with `Power(net, voltage=...)` or `Net(power_net)`. Use stdlib interfaces (`DiffPair`, `I2c`, `Spi`, `Uart`, `Swd`, `Usb2`, ...; `UartPair()` for cross-connected links) when grouped protocol semantics matter. Declare a voltage range on every public `Power` IO unless the API is intentionally generic.

Non-electrical choices use typed `config()`; load physical types (`Voltage`, `Current`, `Resistance`, `Capacitance`, `Inductance`, `Impedance`, `Frequency`, `Temperature`, `Time`, `Power`) from `@stdlib/units.zen`:

```zen
output_voltage = config(Voltage, default="3.3V", allowed=["3.3V", "5V"])
Mode = enum("PULLUP", "PULLDOWN")
mode = config(Mode, default="PULLUP")
```

String defaults auto-convert to the declared type. Expose application-level choices, not internal passive values. Physical values take point values, engineering notation, ranges and tolerances; arithmetic tracks units; equality is strict, use `.matches(...)` for coercive comparison.

## Stable Topology

Configs may change values and `dnp=`, never add, remove or reconnect instances.
- Compute a selected value on one component when the nets do not change.
- Instantiate every mutually exclusive strap or option and DNP the inactive ones; no conditional instantiation.
- Use an IC's internal pull for its default mode; add external bias parts with `dnp=` only for populated alternatives.

Put non-trivial calculations in named functions that cite the datasheet equation or table, and snap with `e3 e6 e12 e24 e48 e96 e192` from `@stdlib/utils.zen`. Use `check`, `warn`, `error` and stdlib checks (prefer `voltage_within(...)` from `@stdlib/checks.zen`) for enforceable constraints rather than comments.

## Public Compatibility

Compatibility covers the public `io()` and `config()` API, entrypoints, behavior, layout and physical assumptions; a build of the current package does not prove consumers still work. If consumers must change, it is breaking: document the migration and use a breaking commit.

## Schematic Position State

`Board(..., schematic = True)` uses `layout_path`; `Project(...)` uses `path`. These KiCad files are persistent state. Preserve legacy `# pcb:sch <ID> ...` comments (add new code above the block; update only the records of a renamed or deleted instance; no `agent-schema` CLI). For a requested legacy migration: `pcb-sch export-kicad <root.zen> --output <fresh-directory>`, enable `schematic = True`, run `pcb apply schematic --no-open <root.zen>` twice; the second must report `schematic unchanged`.

## Packages and Dependencies

The stdlib is toolchain-managed and not in `[dependencies]`. Other packages are declared by `load()` / `Module()` imports; dependency state in `pcb.toml` is tool-managed: never hand-edit resolved versions or use the legacy `pcb update` workflow. `pcb list -m -u` inspects updates, `pcb add -u` takes compatible ones, `pcb list -m -versions <url>` plus `pcb add <url>@<version>` takes a specific or breaking one. Board roots hold workspace and board metadata; registry roots hold reusable members without a root board.

## Style

Match the surrounding code; cleanup rules never apply to `# pcb:sch` records; comment evidence or non-obvious judgment only; no decorative banners. Names: public `io()` uppercase; `config()` lowercase; instances uppercase functional names; differential signals `_P` / `_N` (KiCad pairs nets by suffix). Prefer stdlib generics for passives, discretes, connectors and test points; use `Rectifier`, `Zener` or `Tvs`, not the deprecated `Diode`. For boards use `Board(..., layers=<count>)` (defaults for 2, 4, 6, 8, 10 layers; customize with `outer_copper_weight`, `copper_finish`, `solder_mask_color`, `track_widths`, `via_dimensions`); explicit stackup records only when the defaults are insufficient.

## Completion Evidence

After changing imports or dependencies run `pcb sync`; run `pcb fmt` on changed Zener; `pcb build <path>` for affected entrypoints (`-Wstyle` promotes style advice to warnings); `pcb bom <entrypoint>.zen -f json` only when sourceability matters. Report unverified work.
