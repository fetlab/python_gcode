import logging, ipywidgets
from IPython.display import display

class OutputWidgetHandler(logging.Handler):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, level=kwargs.get('level', logging.NOTSET))
		layout = kwargs.get('layout',
			{
				'width': '100%',
			})
		self.output_widget = ipywidgets.Output(layout=layout)


	def emit(self, record):
		formatted_record = self.format(record)
		new_output = {
			'name':        'stdout',
			'output_type': 'stream',
			'text':        formatted_record + '\n',
		}
		self.output_widget.outputs =  self.output_widget.outputs + (new_output,)


	def show(self):
		display(self.output_widget)



class AccordionHandler(logging.Handler):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, level=kwargs.get('level', logging.NOTSET))
		self._accordion = ipywidgets.Accordion()
		self.output_handler_class = kwargs.get('handler_class', OutputWidgetHandler)
		self.default_handler_args = kwargs.get('handler_args', {})
		self.out_handler = None
		self.shown = False


	def add_fold(self, title, keep_closed=False, **handler_args):
		"""Add a new accordion fold with the given title. If keep_closed is True,
		don't open this fold."""
		new_handler_args = self.default_handler_args.copy()
		new_handler_args.update(handler_args)
		self.out_handler = self.output_handler_class(**new_handler_args)
		self._accordion.children = self._accordion.children + (self.out_handler.output_widget,)
		self._accordion.set_title(-1, title)
		if not keep_closed:
			self._accordion.selected_index = len(self._accordion.children) - 1


	def unfold(self, index=None):
		"""Unfold the fold at the given index, or the last fold if no index is
		provided."""
		self._accordion.selected_index = index if index is not None else len(self._accordion.children) - 1


	def fold(self):
		"""Fold all of the folds."""
		self._accordion.selected_index = None


	def emit(self, record):
		if self.out_handler is None:
			self.add_fold('Messages')
		self.out_handler.emit(record)


	def show(self):
		if not self.shown:
			display(self._accordion)
		self.shown = True
