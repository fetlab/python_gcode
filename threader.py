from copy import deepcopy
from typing import List
from geometry_helpers import GSegment
from fastcore.basics import filter_values
from gcline import GCLine
from gcode import GcodeFile
from rich import print
from rich.pretty import pretty_repr

from logger import rprint, reinit_logging

from printer import Printer
from steps import Steps

print('reload threader')

# --- Options for specific setups ---
# What size does the slicer think the bed is?
effective_bed_size =  79, 220

#Where is the ring center, according to the effective bed coordinate system?
# Note that the ring will be wider than the bed. I got these coordinates via
# the Ender 3 CAD model.
ring_center = 36, 28

#What is the radius of the circle inscribed by the thread outlet from the
# carrier?
ring_radius = 92.5

#Epsilon for various things
thread_epsilon = 1   #Thread segments under this length (mm) get ingored/merged
avoid_epsilon  = 1   #how much room (mm) to leave around segments

"""
Usage notes:
	* The thread should be anchored on the bed such that it doesn't intersect the
		model on the way to its first model-anchor point.
"""

def unprinted(iterable):
	return set(filter(lambda s:not s.printed, iterable))


class Threader:
	def __init__(self, gcode_file:GcodeFile):
		self.gcode_file  = gcode_file
		self.printer     = Printer(effective_bed_size, ring_center, ring_radius)
		self.layer_steps: List[Steps] = []
		self.acclog      = reinit_logging()


	def gcode(self):
		"""Return the gcode for all layers."""
		r = self.gcode_file.preamble.lines.data if self.gcode_file.preamble else []
		for steps_obj in self.layer_steps:
			r.append(GCLine(fake=True, comment=f'==== Start layer {steps_obj.layer.layernum} ===='))
			r.extend(steps_obj.gcode())
		return r


	def route_model(self, thread_list: List[GSegment], start_layer=None, end_layer=None, debug_plot=False):
		if self.layer_steps: raise ValueError("This Threader has been used already")
		self.acclog = reinit_logging(self.acclog)
		self.acclog.show()
		for layer in self.gcode_file.layers[start_layer:end_layer]:
			try:
				self._route_layer(
											thread_list,
											layer,
											self.printer.anchor.copy(z=layer.z),
											debug_plot=debug_plot)
			except:
				self.acclog.unfold()
				raise


	def route_layer(self, thread_list: List[GSegment], layer, start_anchor=None, debug_plot=False):
		"""Goal: produce a sequence of "steps" that route the thread through one
		layer. A "step" is a set of operations that diverge from the original
		gcode; for example, printing all of the non-thread-intersecting segments
		would be one "step".
		"""
		self.acclog = reinit_logging(self.acclog)
		self.acclog.show()
		try:
			self._route_layer(thread_list, layer, start_anchor, debug_plot=debug_plot)
		except:
			self.acclog.unfold()
			raise


	def _route_layer(self, thread_list: List[GSegment], layer, start_anchor=None, debug_plot=False):
		self.printer.layer = layer
		self.printer.z     = layer.z

		self.layer_steps.append(Steps(layer=layer, printer=self.printer, debug_plot=debug_plot))
		steps = self.layer_steps[-1]

		thread = deepcopy(thread_list)

		if thread[0].start_point == self.printer.bed.anchor:
			raise ValueError("Don't set the first thread anchor to the bed anchor")

		#Is the first thread anchor above the top of this layer, or is the last thread anchor
		# below it? If so, we can skip most of the processing; we just need to be
		# sure the print head will avoid the thread.
		bot_z = layer.z - layer.layer_height/2
		top_z = layer.z + layer.layer_height/2
		if thread[0].start_point.z > top_z or thread[-1].end_point.z < bot_z:
			#We want to avoid the computational cost of making geometry from the
			# entire layer if we're not doing anything with it, so we'll just make a
			# rectangle of segments based on the layer extents and avoid that. Might
			# not work if the extents are too big.
			(min_x, min_y), (max_x, max_y) = layer.extents()
			ext_rect = [GSegment(a, b) for a,b in (
				((min_x, min_y, layer.z), (min_x, max_y, layer.z)),
				((min_x, max_y, layer.z), (max_x, max_y, layer.z)),
				((max_x, max_y, layer.z), (max_x, min_y, layer.z)),
				((max_x, min_y, layer.z), (min_x, min_y, layer.z)))]
			with steps.new_step('Move thread to avoid layer extents', debug=False,
											 debug_plot=False):
				self.printer.thread_avoid(ext_rect)
			#Set the Layer's postamble to the entire set of gcode lines so that we
			# correctly generate the output gcode with Steps.gcode()
			layer.postamble = layer.lines
			return steps

		#If we got here, the first thread anchor is inside this layer, so we need
		# to do the actual work

		self.acclog.add_fold(f'Layer {layer.layernum}', keep_closed=True)

		#If there's no start_anchor, we need to assume it's the Bed anchor
		if start_anchor is None:
			thread.insert(0, GSegment(self.printer.bed.anchor, thread[0].start_point))

		rprint(f'Route {len(thread_list)}-segment thread through layer:\n {layer}',
				[f'\t{i}. {tseg}' for i, tseg in enumerate(thread)])

		#Get the thread segments to work on
		thread = layer.flatten_thread(thread)

		rprint('\nFlattened thread:',
			[f'  {i}. {tseg}' for i, tseg in enumerate(thread)])

		#Collect layer segments that involve extrusion
		extrude_segs = [gcseg for gcseg in layer.geometry.segments if gcseg.is_extrude]

		if not thread:
			rprint('Thread not in layer at all')
			with steps.new_step('Thread not in layer') as s:
				s.add(extrude_segs)
			return steps

		#If there's a start anchor (e.g. from the previous layer), check to see if
		# we need to add a thread segment that goes from that anchor to the start
		# point of the thread on this layer. We do so only if the distance from the
		# start anchor to the thread start point is greater than epsilon. If it's
		# not long enough, just move the first thread point to be the start anchor.
		if start_anchor:
			rprint('+++++ START ANCHOR:', start_anchor)
			start_anchor = start_anchor.copy(z=layer.z)
			layer.start_anchor = start_anchor
			if (sdist := start_anchor.distance(thread[0].start_point.copy(z=layer.z))) > thread_epsilon:
				thread.insert(0, GSegment(start_anchor, thread[0].start_point, z=layer.z))
				rprint(f'Added start anchor seg: {thread[0]}')
			else:
				rprint(f'Start anchor to first thread point only {sdist:.2f} mm, moving thread start point')
				thread[0] = thread[0].copy(start_point=start_anchor, z=layer.z)

		#Snap thread to printed geometry
		snapped_thread = layer.geometry_snap(thread)
		if snapped_thread:
			layer.snapped_thread = snapped_thread
			thread = list(filter(None, snapped_thread.values()))
			rprint('Snapped thread:',
					[(f'  {i}. Old: {o}\n     New: {n}' +
						('' if n is None else f' →({o.end_point.distance(n.end_point):.4f} mm)'))
					for i,(o,n) in enumerate(snapped_thread.items())])

		layer.thread = thread

		rprint(f'{len(thread)} thread segments in this layer:',
			[f'  {i}. {tseg} ({tseg.length():>5.2f} mm)' for i, tseg in enumerate(thread)])

		#Check for printed segments that have more than one thread anchor in them
		anchor_points = ([start_anchor] if start_anchor else []) + [tseg.end_point for tseg in thread]
		anchor_segs = {a: a.intersecting(layer.geometry.segments) for a in anchor_points}
		multi_anchor = filter_values(
			{seg: seg.intersecting(anchor_points) for seg in layer.geometry.segments},
			lambda anchors: len(anchors) > 1)
		if multi_anchor:
			rprint('[red]WARNING:[/] some segments contain more than one anchor:', pretty_repr(multi_anchor))
		else:
			rprint('Anchors fixed by segments:', pretty_repr(anchor_segs))

		#Done preprocessing thread; now we can start figuring out what to print and how
		rprint('[yellow]————[/] Start [yellow]————[/]', div=True)

		#Find segments that intersect the incoming thread anchor (if there is one)
		# so we can print those separately to fix the anchor in place. This will be
		# the snapped start point of the first thread segment. We need to move the
		# thread so only the anchor gets printed over, not the rest of the thread.
		if start_anchor:
			a = thread[0].start_point if thread else start_anchor
			anchorsegs = [seg for seg in layer.geometry.segments if a in seg]
			if anchorsegs:
				rprint(f'{len(anchorsegs)} segments intersecting start anchor {a}:',
						anchorsegs, indent=2)
				with steps.new_step(f"Move thread to avoid {len(anchorsegs)} segments fixing start anchor"):
					isecs = self.printer.thread_avoid(anchorsegs)
					if isecs: raise ValueError("Couldn't avoid anchor segments???")
				with steps.new_step(f"Print {len(anchorsegs)} anchor-fixing segments") as s:
					s.add(anchorsegs)
			elif a != self.printer.bed.anchor:
				rprint(f"[yellow]No segments contain the start anchor[/] {a}")

		#Drop thread segments that are too short to worry about
		thread = [tseg for tseg in thread if tseg.length() > thread_epsilon]
		if (t1:=len(thread)) != (t2:=len(layer.thread)):
			rprint(f'Dropped {t2-t1} thread segs due to being shorter than {thread_epsilon}',
					f'now {t1} left')
			if t1 > 0: rprint('\n'.join([f'  {tseg}' for tseg in thread]))

		#Find geometry that will not be intersected by any thread segments
		to_print = unprinted(layer.non_intersecting(thread) if thread else layer.geometry.segments)
		rprint(f'Layer has {len(unprinted(extrude_segs))} unprinted extruding segments,'
				f'with {len(to_print)} not intersecting thread path.')

		self.printer.avoid_and_print(steps, to_print)

		if thread:
			if not {s for s in layer.geometry.segments if not s.printed}:
				rprint(f'Nothing left to print, so not processing {len(thread)} thread segments:',
						thread)
			else:
				rprint(f"[red]———[/] Now process {len(thread)} thread segments [red]———[/]")
				self.debug_threads = thread

				#At this point we've printed everything that does not intersect the
				# thread path. Now we need to work with the individual thread segments
				# one by one:
				# 1. Move the ring so the thread crosses the next anchor point
				# 2. Print gcode segments that intersect this part of the thread, but
				#    that don't intersect:
				#    - the anchor->ring trajectory
				#    - the future thread path
				#    except where those intersections are only at the anchor point iself.
				for i,thread_seg in enumerate(thread):
					rprint(f'[yellow]————[/] Thread {i}: {thread_seg} [yellow]————[/]')

					anchor = thread_seg.end_point

					with steps.new_step(f'Move thread to overlap anchor at {anchor}') as s:
						self.printer.thread_intersect(anchor)

					#Find and print the segment that fixes the thread at the anchor point
					anchorsegs = [seg for seg in unprinted(layer.geometry.segments) if anchor in seg]
					if not anchorsegs: raise ValueError('No unprinted segments overlap anchor')
					with steps.new_step(f'Print {len(anchorsegs)} segment{"s" if len(anchorsegs) > 1 else ""} to fix anchor') as s:
						s.add(anchorsegs)

					#Get non-printed segments that overlap the current thread segment. We
					# want to print these to fix the thread in place.
					to_print = unprinted(layer.intersecting(thread_seg))
					rprint(f'{len(to_print)} unprinted segments intersecting this thread segment')

					#Find gcode segments that intersect future thread segments; we don't
					# want to print these yet, so remove them
					avoid = unprinted(layer.intersecting(thread[i+1:]))
					rprint(f'{len(avoid)} unprinted segments intersecting future thread segments')
					to_print -= avoid

					if to_print:
						self.printer.avoid_and_print(steps, to_print)
						to_print = set()

				# --- Print what's left
				remaining = {s for s in layer.geometry.segments if not s.printed}
				if not remaining == to_print:
					rprint('[red]Odd:\n  remaining - to_print:', remaining - to_print, indent=4)
					rprint('  to_print - remaining:', to_print - remaining, indent=4)
				if remaining:
					self.printer.avoid_and_print(steps, remaining, '(remaining)')

		rprint('[yellow]Done routing this layer[/];',
				len([s for s in layer.geometry.segments if not s.printed]),
				'gcode lines left')
		rprint(f'Printer state: {self.printer}')

		return steps
