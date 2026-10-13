"""EFX Parameter 1-12 mean different things for each of the 40 effect types (shared by the patch and the performance editors)."""

from jv_studio.core import params


def apply_efx_meanings(controls, efx_type_value):
    """Name the twelve EFX knobs after the chosen effect type and grey out the ones it doesn't use. `controls` is {n: KnobControl} for n in 1..12. Only names, tooltips and the
    knob's travel change; the readout keeps showing (and the patch or performance keeps holding) the real value."""
    efx = params.load_table().efx_type(efx_type_value)
    for n, control in controls.items():
        meaning = efx.param(n) if efx is not None else params.EfxParam(n, f"EFX Parameter {n}")
        used = meaning.name is not None
        control.set_name(meaning.name if used else "(not used)")
        control.setEnabled(used)
        control.setToolTip(
            f"{meaning.name} ({efx.name}): {meaning.min} to {meaning.max}.\nDrag to turn. Shift: fine. Double-click: reset. Click and type for an exact value." if used and efx is not None else ""
        )
        control.set_travel(meaning.min, meaning.max)
