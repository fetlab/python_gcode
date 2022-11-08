import rich.jupyter, rich.terminal_theme
from IPython.display import HTML, display
from rich.console import Console
from rich.theme import Theme
from rich.segment import Segment


def _dict2format(style):
	return '<{container} style="{style}">{{code}}</{container}>'.format(
		container=style['_container'],
		style=';'.join((f'{k}:{v}' for k,v in style.items() if k[0] != '_')))


class RichJupyterRenderer:
	_default_html_style = {
		'_container':  'pre',
		'white-space': 'pre',
		'overflow-x':  'auto',
		'line-height': 'normal',
		'font-family': "Menlo,'DejaVu Sans Mono',consolas,'Courier New',monospace",
	}

	def __init__(self, *args, **kwargs):
		self.console = kwargs.get('console', Console(force_jupyter=True, theme=Theme()))
		self.theme = kwargs.get('theme', rich.terminal_theme.DEFAULT_TERMINAL_THEME)

		self.style = self._default_html_style.copy()
		self.style.update(kwargs.get('html_style', {}))
		self.html_format = _dict2format(self.style)


	def _segments_to_html(self, segments, html_style=None):
		def escape(text: str) -> str:
			"""Escape html."""
			return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

		fragments = []
		for text, style, control in Segment.simplify(segments):
			if control:
				continue
			text = escape(text)
			if style:
				rule = style.get_html_style(self.theme)
				text = f'<span style="{rule}">{text}</span>' if rule else text
				if style.link:
					text = f'<a href="{style.link}" target="_blank">{text}</a>'
			fragments.append(text)

		if html_style:
			s = self.style.copy()
			s.update(html_style)
			html_format = _dict2format(s)
		else:
			html_format = self.html_format

		print('html_format:', html_format)

		code = "".join(fragments)
		html = html_format.format(code=code)

		return html


	def rich_to_html(self, rtext, style=None):
		return self._segments_to_html(
				self.console.render(rtext),
				html_style=style or {})


	def display_html(self, rtext, style=None):
		display(HTML(self.rich_to_html(rtext, style)))
