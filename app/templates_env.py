"""Instance Jinja2Templates partagée avec tous les filtres personnalisés."""
import markupsafe
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

# Filtres globaux
templates.env.globals["enumerate"] = enumerate

def _nl2br(value):
    escaped = markupsafe.escape(value)
    return markupsafe.Markup(str(escaped).replace('\n', '<br>\n'))

templates.env.filters["nl2br"] = _nl2br
