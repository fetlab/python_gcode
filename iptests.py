import threader, gcode

g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
		layer_class=threader.TLayer)
layer = g.layers[0]
layer.add_geometry()
p3 = list(layer.parts.values())[3]
l1 = next(l for l in p3 if l.is_xyextrude()).lineno
l2 = next(l for l in reversed(p3) if l.is_xyextrude()).lineno

segs = [s for s in layer.geometry.segments if s.line1.lineno >= l1 and s.line2.lineno <= l2]
