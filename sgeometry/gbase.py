from .gcast import gcast
import skgeom as sg

class _GBase:
	@gcast
	def intersection(self, other):
		return sg.intersection(self, other)

	@gcast
	def intersection2d(self, other):
		return self.as2d().intersection(other.as2d())
