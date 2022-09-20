import logging, rich.jupyter, rich.terminal_theme
from lablogging import OutputWidgetHandler
from IPython.display import HTML
from rich.console import Console
from rich.theme import Theme
from rich.segment import Segment

def _dict2format(style):
	return '<{container} style="{style}">{{code}}</{container}>'.format(
		container=style['_container'],
		style=';'.join((f'{k}:{v}' for k,v in style.items() if k[0] != '_')))


class RichOutputWidgetHandler(OutputWidgetHandler):
	_default_html_style = {
		'_container':  'pre',
		'white-space': 'pre',
		'overflow-x':  'auto',
		'line-height': 'normal',
		'font-family': "Menlo,'DejaVu Sans Mono',consolas,'Courier New',monospace",
	}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, level=kwargs.get('level', logging.NOTSET))
		self.console = kwargs.get('console', Console(force_jupyter=True, theme=Theme()))
		self.theme = kwargs.get('theme', rich.terminal_theme.DEFAULT_TERMINAL_THEME)

		self.style = RichOutputWidgetHandler._default_html_style.copy()
		self.style.update(kwargs.get('html_style', {}))
		self.html_format = _dict2format(self.style)


	def _render_segments(self, segments, html_style=None):
		def escape(text: str) -> str:
			"""Escape html."""
			return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

		fragments = []
		append_fragment = fragments.append
		for text, style, control in Segment.simplify(segments):
			if control:
				continue
			text = escape(text)
			if style:
				rule = style.get_html_style(self.theme)
				text = f'<span style="{rule}">{text}</span>' if rule else text
				if style.link:
					text = f'<a href="{style.link}" target="_blank">{text}</a>'
			append_fragment(text)

		if html_style:
			s = self.style.copy()
			s.update(html_style)
			html_format = _dict2format(s)
		else:
			html_format = self.html_format

		code = "".join(fragments)
		html = html_format.format(code=code)

		return html


	def emit(self, record):
		style = record.__dict__.get('style', {})
		div   = record.__dict__.get('div', '')

		html  = self._render_segments(
			self.console.render(self.format(record)),
			html_style=style)

		#Append to the existing output if it exists and we didn't ask for a new divider
		outs = self.output_widget.outputs
		if (not div) and outs and 'text/html' in outs[-1]['data']:
			self.output_widget.outputs[-1]['data']['text/html'] += html
			self.output_widget.send_state('outputs')
		else:
			if isinstance(div, str) and '<' in div and '>' in div:
				html = div + html
			self.output_widget.append_display_data(HTML(html))
