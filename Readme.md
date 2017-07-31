# Python gcode parser
Some simple code to parse and manipulate gcode. It parses a gcode file
into layers (based either on Cura's "LAYER:0" comments or on changes
in Z) and allows manipulations such as shifting.

## Example

### Input file

```gcode
M190 S70.000000
M109 S220.000000
G21        ;metric values
G90        ;absolute positioning
M82        ;set extruder to absolute mode
;Put printing message on LCD screen
M117 Printing...

;LAYER:0
G0 F9000 X140.000 Y128.500 Z0.300
G1 F1200 X158.000 Y128.500 E0.33859
;LAYER:1
G0 F9000 X153.400 Y133.100 Z0.500
G1 F1620 X153.400 Y141.900 E8.79104
;LAYER:2
G0 F9000 X153.400 Y141.900 Z0.700
G1 F2100 X144.600 Y141.900 E11.98867
```

### Example usage
```python
>>> import gcode
>>> g = gcode.Gcode('/Users/dlaics/r/fabric/test.gcode')
>>> g
<Gcode with 3 layers>
>>> g.layers
[<Layer 0 at Z=0.3, 2 lines>,
 <Layer 1 at Z=0.5, 2 lines>,
 <Layer 2 at Z=0.7, 2 lines>]
>>> g.layers[1].set_preamble('M106 S0   ;Turn fan off for this layer')
>>> g.layers[1].set_postamble('M106 S255   ;Turn fan back on')
>>> g.shift(1,Z=.15)
>>> g.layers
[<Layer 0 at Z=0.3, 2 lines>,
 <Layer 1 at Z=0.65, 2 lines>,
 <Layer 2 at Z=0.85, 2 lines>]
>>> g.construct('out.gcode')
```
