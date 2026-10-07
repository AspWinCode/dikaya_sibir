"""EmailTemplateService._render — HTML output must be XSS-escaped, plain
text/subject must not be (regression test for the S701 autoescape=False fix:
a stored-XSS risk if a context value like a record's "ФИО" field ever
contains `<script>`, since body_html is both emailed and shown back to an
admin in the template preview UI)."""

from types import SimpleNamespace

from app.services.email_templates import EmailTemplateService


def _render(subject: str, body_html: str, body_text: str | None, context: dict) -> object:
    svc = EmailTemplateService(db=None)  # _render never touches self._db
    template = SimpleNamespace(subject=subject, body_html=body_html, body_text=body_text)
    return svc._render(template, context)


class TestRenderEscaping:
    def test_body_html_escapes_html_special_characters(self) -> None:
        payload = {"name": "<script>alert(1)</script>"}
        result = _render("Hi", "<p>Hello, {{ name }}!</p>", None, payload)
        assert "<script>" not in result.body_html
        assert "&lt;script&gt;" in result.body_html

    def test_subject_is_not_html_escaped(self) -> None:
        result = _render("Order #{{ n }} & more", "<p>x</p>", None, {"n": "5"})
        assert result.subject == "Order #5 & more"

    def test_body_text_is_not_html_escaped(self) -> None:
        result = _render("Hi", "<p>x</p>", "Re: {{ topic }}", {"topic": "A & B <ok>"})
        assert result.body_text == "Re: A & B <ok>"

    def test_body_html_with_no_special_characters_is_unaffected(self) -> None:
        result = _render("Hi", "<p>Hello, {{ name }}!</p>", None, {"name": "Иван"})
        assert result.body_html == "<p>Hello, Иван!</p>"
