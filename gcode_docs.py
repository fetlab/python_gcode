import sys, os, glob, yaml, re, textwrap, pprint
from yaml import CLoader as Loader, CDumper as Dumper

class GCodeDocs():
	def __init__(self, docpath='./MarlinDocumentation/_gcode'):
		"""Load all documentation, returning a dict with a gCode linked to
		the documentation for that code."""
		self.gcode_docs = {}
		if os.path.exists(docpath):
			for dfile in glob.glob(os.path.join(docpath, '*.md')):
				with open(dfile) as f:
					#The documentation section appears to not actually be valid
					# YAML, so manually split the file first
					_, sec1, docstr = re.split('^---$', f.read(), flags=re.M)
					tags = yaml.load(sec1, Loader=yaml.Loader)
					tags['docstr'] = docstr
					for code in tags['codes']:
						self.gcode_docs[code] = tags


	def doc(self, gcode):
		"""Return the documentation data structure assocated with the
		given gcode."""
		return self.gcode_docs.get(gcode)


	def pdoc(self, gcode, verbose=False):
		"""Print the documentation associated with the given gcode."""
		if not verbose:
			print('{}: {}'.format(gcode, self.gcode_docs[gcode]['brief']))
		else:
			pprint.pprint(self.gcode_docs[gcode])
