#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GCA - Gestão de Codificação Assistida
Gerador do Documento Técnico Completo (PDF)
Versão 2.0 - 08/04/2026
Autor: Luiz Carlos Pielak
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, Flowable, HRFlowable
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ============================================================
# CONSTANTS
# ============================================================
OUTPUT_PATH = "/home/luiz/GCA/GCA_DOC_COMPLETO_08_04.pdf"
LOGO_PATH = "/home/luiz/GCA/logogca.png"

VIOLET = HexColor("#7c3aed")
VIOLET_LIGHT = HexColor("#a78bfa")
VIOLET_DARK = HexColor("#5b21b6")
EMERALD = HexColor("#10b981")
EMERALD_LIGHT = HexColor("#6ee7b7")
AMBER = HexColor("#f59e0b")
RED = HexColor("#ef4444")
BLUE = HexColor("#3b82f6")
DARK = HexColor("#1e1b2e")
DARK2 = HexColor("#16213e")
GRAY_LIGHT = HexColor("#f3f4f6")
GRAY = HexColor("#9ca3af")
GRAY_DARK = HexColor("#4b5563")
WHITE = white

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm


# ============================================================
# STYLES
# ============================================================
def get_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='CoverTitle', fontName='Helvetica-Bold', fontSize=28,
        textColor=VIOLET, alignment=TA_CENTER, spaceAfter=10, leading=34
    ))
    styles.add(ParagraphStyle(
        name='CoverSubtitle', fontName='Helvetica', fontSize=14,
        textColor=GRAY_DARK, alignment=TA_CENTER, spaceAfter=6, leading=18
    ))
    styles.add(ParagraphStyle(
        name='CoverMeta', fontName='Helvetica', fontSize=11,
        textColor=GRAY, alignment=TA_CENTER, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle', fontName='Helvetica-Bold', fontSize=18,
        textColor=VIOLET, spaceBefore=20, spaceAfter=10, leading=22
    ))
    styles.add(ParagraphStyle(
        name='SubsectionTitle', fontName='Helvetica-Bold', fontSize=13,
        textColor=VIOLET_DARK, spaceBefore=14, spaceAfter=6, leading=16
    ))
    styles.add(ParagraphStyle(
        name='SubsubTitle', fontName='Helvetica-Bold', fontSize=11,
        textColor=DARK, spaceBefore=10, spaceAfter=4, leading=14
    ))
    styles.add(ParagraphStyle(
        name='BodyText2', fontName='Helvetica', fontSize=10,
        textColor=DARK, alignment=TA_JUSTIFY, spaceAfter=6, leading=13
    ))
    styles.add(ParagraphStyle(
        name='TableHeader', fontName='Helvetica-Bold', fontSize=9,
        textColor=WHITE, alignment=TA_CENTER, leading=11
    ))
    styles.add(ParagraphStyle(
        name='TableCell', fontName='Helvetica', fontSize=8,
        textColor=DARK, alignment=TA_LEFT, leading=10
    ))
    styles.add(ParagraphStyle(
        name='TableCellCenter', fontName='Helvetica', fontSize=8,
        textColor=DARK, alignment=TA_CENTER, leading=10
    ))
    styles.add(ParagraphStyle(
        name='TOCEntry', fontName='Helvetica', fontSize=11,
        textColor=DARK, spaceBefore=4, spaceAfter=4, leftIndent=20, leading=14
    ))
    styles.add(ParagraphStyle(
        name='TOCSection', fontName='Helvetica-Bold', fontSize=12,
        textColor=VIOLET, spaceBefore=8, spaceAfter=4, leading=15
    ))
    styles.add(ParagraphStyle(
        name='DiagramLabel', fontName='Helvetica', fontSize=8,
        textColor=DARK, alignment=TA_CENTER, leading=10
    ))
    styles.add(ParagraphStyle(
        name='Glossary', fontName='Helvetica', fontSize=9,
        textColor=DARK, alignment=TA_LEFT, leading=12
    ))
    return styles


# ============================================================
# DIAGRAM FLOWABLES
# ============================================================
class FlowDiagram(Flowable):
    """Top-down flow diagram with boxes and arrows."""

    def __init__(self, title, boxes, arrows, width=None, colors=None, box_h=28, gap=18):
        Flowable.__init__(self)
        self.title = title
        self.boxes = boxes  # list of (label, color_key)
        self.arrows = arrows  # list of (from_idx, to_idx, label) or None for auto
        self.diagram_width = width or 16 * cm
        self.box_h = box_h
        self.gap = gap
        self.colors = colors or {}
        self._calc_height()

    def _calc_height(self):
        title_h = 24
        n = len(self.boxes)
        self.height = title_h + n * self.box_h + (n - 1) * self.gap + 20
        self.width = self.diagram_width

    def _get_color(self, key):
        cmap = {
            'violet': VIOLET, 'emerald': EMERALD, 'amber': AMBER,
            'red': RED, 'blue': BLUE, 'dark': DARK,
            'gray': GRAY_DARK, 'violet_light': VIOLET_LIGHT
        }
        return cmap.get(key, VIOLET)

    def draw(self):
        c = self.canv
        x0 = 0
        w = self.diagram_width
        box_w = min(w * 0.7, 12 * cm)
        bx = (w - box_w) / 2
        y = self.height - 20

        # Title
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VIOLET)
        c.drawCentredString(w / 2, y, self.title)
        y -= 24

        positions = []
        for i, (label, color_key) in enumerate(self.boxes):
            col = self._get_color(color_key)
            # Box
            c.setFillColor(col)
            c.setStrokeColor(col)
            c.roundRect(bx, y - self.box_h, box_w, self.box_h, 6, fill=1, stroke=0)
            # Text
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 9)
            lines = label.split('\n')
            text_y = y - self.box_h / 2 - 4 + (len(lines) - 1) * 5
            for line in lines:
                c.drawCentredString(bx + box_w / 2, text_y, line)
                text_y -= 11
            positions.append((bx + box_w / 2, y - self.box_h, y))
            # Arrow to next
            if i < len(self.boxes) - 1:
                ax = bx + box_w / 2
                ay_start = y - self.box_h
                ay_end = y - self.box_h - self.gap
                c.setStrokeColor(GRAY_DARK)
                c.setLineWidth(1.2)
                c.line(ax, ay_start, ax, ay_end + 6)
                # Arrowhead
                c.setFillColor(GRAY_DARK)
                p = c.beginPath()
                p.moveTo(ax - 4, ay_end + 8)
                p.lineTo(ax + 4, ay_end + 8)
                p.lineTo(ax, ay_end)
                p.close()
                c.drawPath(p, fill=1, stroke=0)
                # Arrow label
                if self.arrows and i < len(self.arrows) and self.arrows[i]:
                    c.setFont("Helvetica", 7)
                    c.setFillColor(GRAY_DARK)
                    c.drawString(ax + 6, ay_start - self.gap / 2, self.arrows[i])

            y -= (self.box_h + self.gap)


class ParallelFlowDiagram(Flowable):
    """Top-down diagram with parallel branches."""

    def __init__(self, title, top_boxes, parallel_groups, bottom_boxes, width=None):
        Flowable.__init__(self)
        self.title = title
        self.top_boxes = top_boxes
        self.parallel_groups = parallel_groups  # list of lists of (label, color)
        self.bottom_boxes = bottom_boxes
        self.diagram_width = width or 16 * cm
        self._calc()

    def _calc(self):
        self.box_h = 26
        self.gap = 16
        rows = len(self.top_boxes) + len(self.parallel_groups) + len(self.bottom_boxes)
        self.height = 24 + rows * (self.box_h + self.gap) + 20
        self.width = self.diagram_width

    def _color(self, key):
        cmap = {
            'violet': VIOLET, 'emerald': EMERALD, 'amber': AMBER,
            'red': RED, 'blue': BLUE, 'dark': DARK, 'gray': GRAY_DARK,
        }
        return cmap.get(key, VIOLET)

    def _draw_box(self, c, x, y, w, h, label, color_key):
        col = self._color(color_key)
        c.setFillColor(col)
        c.roundRect(x, y, w, h, 5, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 8)
        lines = label.split('\n')
        ty = y + h / 2 + (len(lines) - 1) * 4
        for ln in lines:
            c.drawCentredString(x + w / 2, ty - 3, ln)
            ty -= 10

    def _arrow_down(self, c, x, y1, y2):
        c.setStrokeColor(GRAY_DARK)
        c.setLineWidth(1)
        c.line(x, y1, x, y2 + 5)
        c.setFillColor(GRAY_DARK)
        p = c.beginPath()
        p.moveTo(x - 3, y2 + 7)
        p.lineTo(x + 3, y2 + 7)
        p.lineTo(x, y2)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    def draw(self):
        c = self.canv
        W = self.diagram_width
        cx = W / 2
        bw = min(W * 0.65, 11 * cm)
        y = self.height - 20

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VIOLET)
        c.drawCentredString(cx, y, self.title)
        y -= 22

        # Top boxes
        for label, col in self.top_boxes:
            bx = (W - bw) / 2
            self._draw_box(c, bx, y - self.box_h, bw, self.box_h, label, col)
            prev_cx = bx + bw / 2
            prev_bottom = y - self.box_h
            y -= (self.box_h + self.gap)
            if y > 0:
                self._arrow_down(c, prev_cx, prev_bottom, y)

        # Parallel groups
        for group in self.parallel_groups:
            n = len(group)
            pw = min((W - 10) / n, 5 * cm)
            total_pw = n * pw + (n - 1) * 6
            start_x = (W - total_pw) / 2
            centers = []
            for i, (label, col) in enumerate(group):
                px = start_x + i * (pw + 6)
                self._draw_box(c, px, y - self.box_h, pw, self.box_h, label, col)
                centers.append(px + pw / 2)
            # arrows from above center to each
            for ctr in centers:
                self._arrow_down(c, ctr, y + self.gap - 2, y)
            prev_bottom = y - self.box_h
            y -= (self.box_h + self.gap)
            # merge arrows
            if self.bottom_boxes:
                for ctr in centers:
                    self._arrow_down(c, ctr, prev_bottom, y)

        # Bottom boxes
        for label, col in self.bottom_boxes:
            bx = (W - bw) / 2
            self._draw_box(c, bx, y - self.box_h, bw, self.box_h, label, col)
            prev_cx = bx + bw / 2
            prev_bottom = y - self.box_h
            y -= (self.box_h + self.gap)
            if y > 0 and label != self.bottom_boxes[-1][0]:
                self._arrow_down(c, prev_cx, prev_bottom, y)


class SequenceDiagram(Flowable):
    """Sequence diagram with actor lifelines and messages."""

    def __init__(self, title, actors, messages, width=None):
        Flowable.__init__(self)
        self.title = title
        self.actors = actors  # [(name, color_key), ...]
        self.messages = messages  # [(from_idx, to_idx, label, is_return), ...]
        self.diagram_width = width or 16 * cm
        self._calc()

    def _calc(self):
        self.actor_h = 26
        self.msg_gap = 22
        self.top_margin = 30
        self.height = self.top_margin + self.actor_h + 10 + len(self.messages) * self.msg_gap + 30
        self.width = self.diagram_width

    def _color(self, key):
        cmap = {
            'violet': VIOLET, 'emerald': EMERALD, 'amber': AMBER,
            'red': RED, 'blue': BLUE, 'dark': DARK, 'gray': GRAY_DARK,
        }
        return cmap.get(key, VIOLET)

    def draw(self):
        c = self.canv
        W = self.diagram_width
        n = len(self.actors)
        spacing = W / (n + 1)
        y = self.height - 10

        # Title
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VIOLET)
        c.drawCentredString(W / 2, y, self.title)
        y -= 22

        # Actor boxes
        actor_xs = []
        for i, (name, col_key) in enumerate(self.actors):
            ax = spacing * (i + 1)
            actor_xs.append(ax)
            bw = max(len(name) * 5.5 + 10, 50)
            col = self._color(col_key)
            c.setFillColor(col)
            c.roundRect(ax - bw / 2, y - self.actor_h, bw, self.actor_h, 4, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(ax, y - self.actor_h / 2 - 3, name)

        lifeline_top = y - self.actor_h
        lifeline_bottom = 10

        # Lifelines (dashed)
        c.setDash(3, 3)
        c.setStrokeColor(GRAY)
        c.setLineWidth(0.5)
        for ax in actor_xs:
            c.line(ax, lifeline_top, ax, lifeline_bottom)
        c.setDash()

        # Messages
        msg_y = lifeline_top - 14
        for from_idx, to_idx, label, is_return in self.messages:
            x1 = actor_xs[from_idx]
            x2 = actor_xs[to_idx]
            if is_return:
                c.setDash(4, 3)
                c.setStrokeColor(GRAY_DARK)
            else:
                c.setDash()
                c.setStrokeColor(DARK)
            c.setLineWidth(1)
            c.line(x1, msg_y, x2, msg_y)

            # Arrowhead
            direction = 1 if x2 > x1 else -1
            c.setFillColor(DARK if not is_return else GRAY_DARK)
            p = c.beginPath()
            p.moveTo(x2, msg_y)
            p.lineTo(x2 - direction * 6, msg_y + 3)
            p.lineTo(x2 - direction * 6, msg_y - 3)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
            c.setDash()

            # Label
            c.setFont("Helvetica", 7)
            c.setFillColor(DARK)
            lx = (x1 + x2) / 2
            c.drawCentredString(lx, msg_y + 5, label)

            msg_y -= self.msg_gap


class StateDiagram(Flowable):
    """State diagram with rounded boxes and transition arrows."""

    def __init__(self, title, states, transitions, width=None):
        Flowable.__init__(self)
        self.title = title
        self.states = states  # [(name, color_key), ...]
        self.transitions = transitions  # [(from_idx, to_idx, label), ...] or auto
        self.diagram_width = width or 16 * cm
        self._calc()

    def _calc(self):
        n = len(self.states)
        self.box_h = 24
        self.gap = 20
        self.height = 26 + n * (self.box_h + self.gap) + 10
        self.width = self.diagram_width

    def _color(self, key):
        cmap = {
            'violet': VIOLET, 'emerald': EMERALD, 'amber': AMBER,
            'red': RED, 'blue': BLUE, 'dark': DARK, 'gray': GRAY_DARK,
        }
        return cmap.get(key, VIOLET)

    def draw(self):
        c = self.canv
        W = self.diagram_width
        cx = W / 2
        bw = min(W * 0.5, 8 * cm)
        y = self.height - 10

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VIOLET)
        c.drawCentredString(cx, y, self.title)
        y -= 24

        positions = []
        for i, (name, col_key) in enumerate(self.states):
            col = self._color(col_key)
            bx = cx - bw / 2
            c.setFillColor(col)
            c.roundRect(bx, y - self.box_h, bw, self.box_h, 10, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(cx, y - self.box_h / 2 - 3, name)
            positions.append((cx, y, y - self.box_h))

            if i < len(self.states) - 1:
                ay1 = y - self.box_h
                ay2 = y - self.box_h - self.gap
                c.setStrokeColor(GRAY_DARK)
                c.setLineWidth(1)
                c.line(cx, ay1, cx, ay2 + 5)
                c.setFillColor(GRAY_DARK)
                p = c.beginPath()
                p.moveTo(cx - 3, ay2 + 7)
                p.lineTo(cx + 3, ay2 + 7)
                p.lineTo(cx, ay2)
                p.close()
                c.drawPath(p, fill=1, stroke=0)
                # Transition label
                if self.transitions and i < len(self.transitions):
                    c.setFont("Helvetica", 7)
                    c.setFillColor(GRAY_DARK)
                    c.drawString(cx + 8, ay1 - self.gap / 2, self.transitions[i])

            y -= (self.box_h + self.gap)


class StateDiagramBranch(Flowable):
    """State diagram with branching paths (fork)."""

    def __init__(self, title, linear_states, fork_label, branches, width=None):
        Flowable.__init__(self)
        self.title = title
        self.linear_states = linear_states  # [(name, color), ...]
        self.fork_label = fork_label
        self.branches = branches  # [[(name, color), ...], [(name, color), ...]]
        self.diagram_width = width or 16 * cm
        self._calc()

    def _calc(self):
        max_branch = max(len(b) for b in self.branches) if self.branches else 0
        n = len(self.linear_states) + 1 + max_branch
        self.box_h = 22
        self.gap = 16
        self.height = 26 + n * (self.box_h + self.gap) + 10
        self.width = self.diagram_width

    def _color(self, key):
        cmap = {
            'violet': VIOLET, 'emerald': EMERALD, 'amber': AMBER,
            'red': RED, 'blue': BLUE, 'dark': DARK, 'gray': GRAY_DARK,
        }
        return cmap.get(key, VIOLET)

    def _draw_box(self, c, x, y, w, h, label, col_key):
        col = self._color(col_key)
        c.setFillColor(col)
        c.roundRect(x, y, w, h, 8, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + w / 2, y + h / 2 - 3, label)

    def _arrow(self, c, x1, y1, x2, y2):
        c.setStrokeColor(GRAY_DARK)
        c.setLineWidth(1)
        c.line(x1, y1, x2, y2 + 5)
        c.setFillColor(GRAY_DARK)
        p = c.beginPath()
        p.moveTo(x2 - 3, y2 + 7)
        p.lineTo(x2 + 3, y2 + 7)
        p.lineTo(x2, y2)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    def draw(self):
        c = self.canv
        W = self.diagram_width
        cx = W / 2
        bw = min(W * 0.45, 7.5 * cm)
        y = self.height - 10

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VIOLET)
        c.drawCentredString(cx, y, self.title)
        y -= 24

        # Linear states
        for i, (name, col) in enumerate(self.linear_states):
            self._draw_box(c, cx - bw / 2, y - self.box_h, bw, self.box_h, name, col)
            y -= (self.box_h + self.gap)
            if i < len(self.linear_states) - 1 or self.branches:
                self._arrow(c, cx, y + self.gap, cx, y)

        # Fork label
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(AMBER)
        c.drawCentredString(cx, y + 6, self.fork_label)
        y -= 8

        # Branches
        nb = len(self.branches)
        branch_w = min((W - 20) / nb, 5.5 * cm)
        total = nb * branch_w + (nb - 1) * 10
        sx = (W - total) / 2

        max_len = max(len(b) for b in self.branches)
        for row in range(max_len):
            for bi, branch in enumerate(self.branches):
                if row < len(branch):
                    name, col = branch[row]
                    bx = sx + bi * (branch_w + 10)
                    self._draw_box(c, bx, y - self.box_h, branch_w, self.box_h, name, col)
                    if row == 0:
                        self._arrow(c, cx, y + self.gap - 6, bx + branch_w / 2, y)
            y -= (self.box_h + self.gap)


# ============================================================
# HEADER / FOOTER
# ============================================================
def header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    w, h = A4

    # Header bar
    canvas_obj.setFillColor(VIOLET)
    canvas_obj.rect(0, h - 1.4 * cm, w, 1.4 * cm, fill=1, stroke=0)

    # Logo in header
    try:
        canvas_obj.drawImage(LOGO_PATH, 0.6 * cm, h - 1.3 * cm, width=1 * cm, height=1 * cm,
                             preserveAspectRatio=True, mask='auto')
    except:
        pass

    canvas_obj.setFillColor(WHITE)
    canvas_obj.setFont("Helvetica-Bold", 10)
    canvas_obj.drawString(2 * cm, h - 1.0 * cm, "GCA - Gestão de Codificação Assistida")

    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawRightString(w - 1 * cm, h - 1.0 * cm, "Documento Técnico v2.0")

    # Footer
    canvas_obj.setFillColor(GRAY)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawString(MARGIN, 0.7 * cm,
                          "Luiz Carlos Pielak | gca.code-auditor.com.br")
    canvas_obj.drawRightString(w - MARGIN, 0.7 * cm,
                               f"08/04/2026 — Página {doc.page}")
    # Footer line
    canvas_obj.setStrokeColor(VIOLET)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN, 1.1 * cm, w - MARGIN, 1.1 * cm)

    canvas_obj.restoreState()


def cover_page(canvas_obj, doc):
    """Draw cover page without header/footer."""
    canvas_obj.saveState()
    w, h = A4

    # Background gradient bar
    canvas_obj.setFillColor(VIOLET)
    canvas_obj.rect(0, h - 4 * cm, w, 4 * cm, fill=1, stroke=0)
    canvas_obj.setFillColor(VIOLET_LIGHT)
    canvas_obj.rect(0, h - 4.15 * cm, w, 0.15 * cm, fill=1, stroke=0)

    # Footer
    canvas_obj.setFillColor(GRAY)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawCentredString(w / 2, 1 * cm, "Luiz Carlos Pielak | gca.code-auditor.com.br")

    canvas_obj.restoreState()


# ============================================================
# TABLE HELPER
# ============================================================
def make_table(headers, rows, col_widths=None, style_override=None):
    """Create a styled table."""
    styles = get_styles()
    header_row = [Paragraph(h, styles['TableHeader']) for h in headers]
    data = [header_row]
    for row in rows:
        data.append([Paragraph(str(c), styles['TableCell']) for c in row])

    if not col_widths:
        avail = PAGE_W - 2 * MARGIN
        col_widths = [avail / len(headers)] * len(headers)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), VIOLET),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    # Alternating rows
    for i in range(1, len(data)):
        if i % 2 == 0:
            base_style.append(('BACKGROUND', (0, i), (-1, i), GRAY_LIGHT))

    if style_override:
        base_style.extend(style_override)

    t.setStyle(TableStyle(base_style))
    return t


# ============================================================
# DOCUMENT BUILDER
# ============================================================
def build_document():
    styles = get_styles()
    story = []
    avail_w = PAGE_W - 2 * MARGIN

    # --------------------------------------------------------
    # CAPA
    # --------------------------------------------------------
    story.append(Spacer(1, 5 * cm))

    # Logo
    if os.path.exists(LOGO_PATH):
        story.append(Image(LOGO_PATH, width=5 * cm, height=5 * cm))
    story.append(Spacer(1, 1.5 * cm))

    story.append(Paragraph("GCA — Gestão de Codificação Assistida", styles['CoverTitle']))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Documento Técnico, Negocial e de Requisitos", styles['CoverSubtitle']))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("Versão 2.0", styles['CoverMeta']))
    story.append(Paragraph("08 de Abril de 2026", styles['CoverMeta']))
    story.append(Paragraph("Autor: Luiz Carlos Pielak", styles['CoverMeta']))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("Status: Em Desenvolvimento", styles['CoverMeta']))

    story.append(PageBreak())

    # --------------------------------------------------------
    # SUMÁRIO
    # --------------------------------------------------------
    story.append(Paragraph("Sumário", styles['SectionTitle']))
    story.append(Spacer(1, 0.3 * cm))

    toc_items = [
        ("1", "Introdução e Visão Geral"),
        ("2", "Stack Tecnológica"),
        ("3", "Infraestrutura e Deploy"),
        ("4", "Requisitos Funcionais (RF-001 a RF-015)"),
        ("5", "Requisitos Não Funcionais (RNF-001 a RNF-008)"),
        ("6", "Regras de Negócio (RN-001 a RN-015)"),
        ("7", "Modelo de Dados (Banco de Dados)"),
        ("8", "Endpoints da API (60+)"),
        ("9", "Questionário Técnico (54 Campos)"),
        ("10", "Pipeline de Verificação Tecnológica"),
        ("11", "Arquitetura de Agentes IA (8 Agentes)"),
        ("12", "Diagramas de Fluxo"),
        ("13", "Diagramas de Sequência"),
        ("14", "Diagramas de Estado"),
        ("15", "Pipeline n8n"),
        ("16", "Mapa de Telas (29 Páginas)"),
        ("17", "Serviços do Backend (17 Serviços)"),
        ("18", "Glossário"),
    ]
    for num, title in toc_items:
        story.append(Paragraph(f"<b>{num}.</b>  {title}", styles['TOCEntry']))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 1. INTRODUÇÃO E VISÃO GERAL
    # --------------------------------------------------------
    story.append(Paragraph("1. Introdução e Visão Geral", styles['SectionTitle']))

    story.append(Paragraph("<b>O que é o GCA</b>", styles['SubsectionTitle']))
    story.append(Paragraph(
        "O GCA (Gestão de Codificação Assistida) é uma plataforma inteligente para governança e "
        "geração automatizada de código-fonte. Combina análise de requisitos, validação por "
        "inteligência artificial e os 7 Pilares de Qualidade para garantir que todo projeto de "
        "software entregue atenda a padrões rigorosos de qualidade, segurança e conformidade.",
        styles['BodyText2']))

    story.append(Paragraph("<b>Objetivo do Sistema</b>", styles['SubsectionTitle']))
    story.append(Paragraph(
        "Automatizar o ciclo completo de análise de requisitos → validação tecnológica → geração de "
        "código, eliminando gaps de comunicação entre stakeholders e equipe técnica. O sistema "
        "recebe um questionário de 54 campos, executa verificação tecnológica em 8 fases, analisa "
        "cada pilar via agentes IA especializados, gera o Objeto Contexto Global (OCG) e, com "
        "aprovação do administrador, prossegue para geração de código.",
        styles['BodyText2']))

    story.append(Paragraph("<b>Os 7 Pilares de Qualidade</b>", styles['SubsectionTitle']))
    pillar_data = [
        ("P1", "Contexto de Negócio", "10%", "Objetivos, ROI, caso de negócio, alinhamento estratégico"),
        ("P2", "Regras e Conformidade", "15%", "LGPD, GDPR, regulações setoriais, residência de dados"),
        ("P3", "Requisitos Funcionais", "20%", "Features, user stories, integrações, escopo do MVP"),
        ("P4", "Requisitos Não Funcionais", "20%", "Performance, escalabilidade, disponibilidade, SLA"),
        ("P5", "Arquitetura", "15%", "Design, padrões, modularidade, topologia do sistema"),
        ("P6", "Dados", "10%", "Modelo de dados, armazenamento, migrações, backup"),
        ("P7", "Segurança", "10%", "Autenticação, criptografia, vulnerabilidades. BLOQUEANTE se < 70"),
    ]
    cw = [avail_w * 0.06, avail_w * 0.18, avail_w * 0.08, avail_w * 0.68]
    story.append(make_table(["ID", "Pilar", "Peso", "Foco da Avaliação"], pillar_data, cw))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Fluxo Principal</b>", styles['SubsectionTitle']))
    story.append(Paragraph(
        "Questionário (54 campos) → Verificação Tecnológica (8 fases) → Agentes IA (8 agentes, "
        "7 em paralelo) → OCG (Objeto Contexto Global) → Avaliação Administrativa → CodeGen",
        styles['BodyText2']))

    story.append(Paragraph("<b>Repositório Git</b>", styles['SubsectionTitle']))
    story.append(Paragraph(
        "URL: https://github.com/Pielak/GCA.git — 82 commits, branches: master (produção) e main (desenvolvimento).",
        styles['BodyText2']))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 2. STACK TECNOLÓGICA
    # --------------------------------------------------------
    story.append(Paragraph("2. Stack Tecnológica", styles['SectionTitle']))

    stack_data = [
        ("Backend", "Python 3.11+, FastAPI 0.104, SQLAlchemy 2.0, Pydantic 2.5"),
        ("Frontend", "React 18.3, TypeScript 5.6, Vite 6.0, Tailwind 3.4, Zustand 5.0, TanStack Query 5.61"),
        ("Banco de Dados", "PostgreSQL 16 (asyncpg), Redis 7"),
        ("Inteligência Artificial", "Anthropic SDK 0.25 (Claude Opus 4.6), OpenAI, Gemini, DeepSeek, Grok"),
        ("Automação", "n8n (workflow automation, Docker)"),
        ("Containerização", "Docker + Docker Compose (5 serviços)"),
        ("Proxy / CDN", "Cloudflare Tunnel (HTTPS, proteção DDoS)"),
        ("Testes", "pytest 7.4, pytest-asyncio, pytest-cov"),
        ("Formatação / Lint", "black, flake8, mypy, isort"),
        ("Controle de Versão", "Git + GitHub (CI/CD com GitHub Actions)"),
    ]
    cw = [avail_w * 0.22, avail_w * 0.78]
    story.append(make_table(["Camada", "Tecnologias"], stack_data, cw))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 3. INFRAESTRUTURA E DEPLOY
    # --------------------------------------------------------
    story.append(Paragraph("3. Infraestrutura e Deploy", styles['SectionTitle']))

    story.append(Paragraph("<b>Docker Compose — 5 Serviços</b>", styles['SubsectionTitle']))
    docker_data = [
        ("postgres", "postgres:16-alpine", "5432", "Banco de dados principal (asyncpg)"),
        ("redis", "redis:7-alpine", "6379 (interno)", "Cache e filas de mensagens"),
        ("backend", "FastAPI (Python 3.11)", "8000", "API REST, autenticação, lógica de negócio"),
        ("frontend", "node:20-alpine (Vite)", "5173", "Interface React/TypeScript"),
        ("n8n", "n8nio/n8n:latest", "5678", "Automação de workflows, integração IA"),
    ]
    cw = [avail_w * 0.12, avail_w * 0.22, avail_w * 0.14, avail_w * 0.52]
    story.append(make_table(["Serviço", "Imagem", "Porta", "Descrição"], docker_data, cw))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>URLs de Produção</b>", styles['SubsectionTitle']))
    url_data = [
        ("Frontend", "gca.code-auditor.com.br", "Interface web (React)"),
        ("API", "api.code-auditor.com.br", "Backend REST (FastAPI)"),
        ("n8n", "n8n.code-auditor.com.br", "Painel de automação"),
    ]
    cw = [avail_w * 0.15, avail_w * 0.35, avail_w * 0.50]
    story.append(make_table(["Serviço", "URL", "Descrição"], url_data, cw))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Hardware do Servidor</b>", styles['SubsectionTitle']))
    story.append(Paragraph(
        "Processador: Intel Core i5-13400 (10 cores) | Memória: 40 GB RAM DDR5 | "
        "Armazenamento: NVMe 238 GB + SSD 440 GB (/mnt/dados) | "
        "Sistema: Linux Mint 22.3 Zena (kernel 6.17.0-20-generic)",
        styles['BodyText2']))

    story.append(Paragraph("<b>Auto-start e Proxy</b>", styles['SubsectionTitle']))
    story.append(Paragraph(
        "O serviço é inicializado automaticamente via systemd (gca.service, enabled) com loginctl linger "
        "habilitado. O Cloudflare Tunnel atua como reverse proxy, provendo HTTPS e proteção DDoS. "
        "O servidor NÃO está hospedado em cloud — é uma máquina local com proxy reverso.",
        styles['BodyText2']))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 4. REQUISITOS FUNCIONAIS
    # --------------------------------------------------------
    story.append(Paragraph("4. Requisitos Funcionais (RF-001 a RF-015)", styles['SectionTitle']))

    rf_data = [
        ("RF-001", "Convite de Usuário", "Alta",
         "Admin convida novos usuários com senha temporária e token de convite. Expiração em 7 dias."),
        ("RF-002", "Primeiro Acesso", "Alta",
         "Usuário com first_access_completed=false é forçado a definir senha permanente via modal."),
        ("RF-003", "Login e Autenticação", "Alta",
         "Login via email/senha, JWT (access_token 30min, refresh_token 7d), bootstrap-admin."),
        ("RF-004", "Reset de Senha", "Alta",
         "Solicitação por email, token temporário, confirmação com nova senha validada."),
        ("RF-005", "Gerenciamento de Projetos", "Alta",
         "CRUD de projetos: listar, criar, atualizar, arquivar. Admin vê todos, GP vê os seus."),
        ("RF-006", "Questionário Técnico", "Alta",
         "54 campos em 8 seções (blocos A.1 a A.12), mapeados nos 7 pilares. Timer de 5 dias."),
        ("RF-007", "Verificação Tecnológica", "Alta",
         "Pipeline de 8 fases com 8 matrizes de compatibilidade. Severidades: BLOCKER a INFO."),
        ("RF-008", "Agentes IA", "Alta",
         "8 agentes (Analyzer + 7 Pillar Specialists + Consolidator) via Anthropic SDK (Claude Opus 4.6)."),
        ("RF-009", "Geração de OCG", "Alta",
         "Objeto Contexto Global com scores por pilar, stack recommendation, compliance, riscos."),
        ("RF-010", "Avaliação de Artefatos", "Média",
         "Avaliação por 7 pilares com scores 0-100, P7 bloqueante se < 70, status final."),
        ("RF-011", "Geração de Código", "Média",
         "CodeGen a partir do OCG aprovado, estrutura de projeto, testes, CI/CD, documentação."),
        ("RF-012", "Criação de Projeto Externo", "Alta",
         "GP externo solicita projeto via link com token (5 dias). 46 perguntas, análise IA, aprovação admin."),
        ("RF-013", "Dashboard Administrativo", "Média",
         "Métricas, gráficos, listagem de projetos pendentes, usuários ativos, alertas do sistema."),
        ("RF-014", "Auditoria Global", "Alta",
         "Log imutável com hash encadeado (blockchain-like). Registra todas as ações críticas."),
        ("RF-015", "Suporte e Tickets", "Baixa",
         "Sistema de tickets com severidade, SLA de resposta, integração email."),
    ]
    cw = [avail_w * 0.08, avail_w * 0.16, avail_w * 0.07, avail_w * 0.69]
    story.append(make_table(["ID", "Nome", "Prioridade", "Descrição"], rf_data, cw))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 5. REQUISITOS NÃO FUNCIONAIS
    # --------------------------------------------------------
    story.append(Paragraph("5. Requisitos Não Funcionais (RNF-001 a RNF-008)", styles['SectionTitle']))

    rnf_data = [
        ("RNF-001", "Performance", "Alta",
         "Tempo de resposta da API < 500ms (p95). Análise IA completa em < 5 minutos."),
        ("RNF-002", "Escalabilidade", "Média",
         "Suporte a 100 projetos simultâneos, 500 usuários concorrentes. Horizontal scaling via Docker."),
        ("RNF-003", "Disponibilidade", "Alta",
         "99.5% uptime (excluindo manutenção programada). Auto-start com systemd."),
        ("RNF-004", "Segurança", "Alta",
         "JWT com expiração, bcrypt para senhas, CORS configurado, rate limiting, Cloudflare DDoS."),
        ("RNF-005", "Manutenibilidade", "Média",
         "Código formatado (black/flake8), tipado (mypy), cobertura de testes > 80%."),
        ("RNF-006", "Compatibilidade", "Média",
         "Chrome 90+, Firefox 88+, Safari 14+, Edge 90+. Responsivo (desktop e tablet)."),
        ("RNF-007", "Observabilidade", "Média",
         "Logs estruturados, audit trail com hash, alertas automáticos, métricas de dashboard."),
        ("RNF-008", "Backup e Recuperação", "Alta",
         "PostgreSQL: backup diário automático. Redis: persistência AOF. Git: repositório remoto."),
    ]
    cw = [avail_w * 0.09, avail_w * 0.14, avail_w * 0.07, avail_w * 0.70]
    story.append(make_table(["ID", "Nome", "Prioridade", "Descrição"], rnf_data, cw))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 6. REGRAS DE NEGÓCIO
    # --------------------------------------------------------
    story.append(Paragraph("6. Regras de Negócio (RN-001 a RN-015)", styles['SectionTitle']))

    rn_data = [
        ("RN-001", "Validação de Senha",
         "Mínimo 10 caracteres, 1 maiúscula, 1 dígito, 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)."),
        ("RN-002", "Primeiro Acesso Obrigatório",
         "Usuário com first_access_completed=false DEVE definir senha permanente antes de acessar o sistema."),
        ("RN-003", "Token de Convite — 7 Dias",
         "Convites expiram em 7 dias. Após expirar, é necessário gerar novo convite."),
        ("RN-004", "Admin Não Pode Desativar a Si Mesmo",
         "Endpoint de desativação verifica se actor_id != target_id para admins."),
        ("RN-005", "Pilar 7 (Segurança) Bloqueante",
         "Se p7_security_score < 70, o artefato é BLOQUEADO e code_generation_allowed=false."),
        ("RN-006", "Token de Projeto Externo — 5 Dias",
         "Links para questionário externo expiram em 5 dias (120 horas)."),
        ("RN-007", "Timer de Preenchimento — 5 Dias",
         "Countdown de 5 dias exibido no questionário. Persistido em localStorage e backend."),
        ("RN-008", "Questionário — Draft Automático",
         "Respostas salvas como draft a cada 30 segundos. Aviso ao sair sem salvar."),
        ("RN-009", "Permissões por Papel",
         "Admin vê todos os projetos. GP vê apenas os seus. Membros veem projetos atribuídos."),
        ("RN-010", "Número de Requisição Único",
         "Formato REQ-YYYYMMDD-XXXXX, gerado automaticamente no submit do questionário."),
        ("RN-011", "Aprovação Cria Projeto Imediato",
         "Ao aprovar um projeto externo, o sistema cria imediatamente o projeto, organização e membros."),
        ("RN-012", "JWT — Access Token 30min",
         "Access token expira em 30 minutos. Refresh token expira em 7 dias."),
        ("RN-013", "Audit Log Imutável",
         "Cada entrada do audit_log_global contém previous_hash, formando cadeia verificável."),
        ("RN-014", "Email em Todas as Etapas",
         "Notificações por email em: convite, aprovação, rejeição, reset de senha, alerta de segurança."),
        ("RN-015", "Análise IA Assíncrona",
         "Análise do questionário via n8n/agentes é assíncrona. GP recebe resposta imediata e acompanha status."),
    ]
    cw = [avail_w * 0.08, avail_w * 0.20, avail_w * 0.72]
    story.append(make_table(["ID", "Nome", "Descrição"], rn_data, cw))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 7. MODELO DE DADOS
    # --------------------------------------------------------
    story.append(Paragraph("7. Modelo de Dados (Banco de Dados)", styles['SectionTitle']))
    story.append(Paragraph(
        "PostgreSQL 16.13 — 26 tabelas, 325+ colunas. Tabelas agrupadas por domínio.",
        styles['BodyText2']))

    # --- Core Tables ---
    story.append(Paragraph("<b>7.1 Tabelas Core</b>", styles['SubsectionTitle']))

    story.append(Paragraph("<b>users</b> (11 colunas)", styles['SubsubTitle']))
    users_cols = [
        ("id", "UUID", "PK"),
        ("email", "VARCHAR", "UNIQUE, NOT NULL"),
        ("password_hash", "VARCHAR", "bcrypt hash"),
        ("full_name", "VARCHAR", "nullable"),
        ("is_active", "BOOLEAN", "default true"),
        ("is_admin", "BOOLEAN", "default false"),
        ("first_access_completed", "BOOLEAN", "fluxo primeiro acesso"),
        ("password_changed_at", "TIMESTAMP", "nullable"),
        ("last_login_at", "TIMESTAMP", "nullable"),
        ("created_at", "TIMESTAMP", "auto"),
        ("updated_at", "TIMESTAMP", "auto"),
    ]
    cw = [avail_w * 0.25, avail_w * 0.20, avail_w * 0.55]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], users_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>organizations</b> (7 colunas)", styles['SubsubTitle']))
    org_cols = [
        ("id", "UUID", "PK"),
        ("name", "VARCHAR", "NOT NULL"),
        ("slug", "VARCHAR", "UNIQUE"),
        ("description", "VARCHAR", "nullable"),
        ("owner_id", "UUID", "FK → users"),
        ("is_active", "BOOLEAN", "nullable"),
        ("created_at / updated_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], org_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>projects</b> (10 colunas)", styles['SubsubTitle']))
    proj_cols = [
        ("id", "UUID", "PK"),
        ("organization_id", "UUID", "FK → organizations"),
        ("name", "VARCHAR", "NOT NULL"),
        ("slug", "VARCHAR", "NOT NULL"),
        ("description", "VARCHAR", "nullable"),
        ("status", "VARCHAR", "DRAFT, PROVISIONING, ACTIVE, ARCHIVED"),
        ("wizard_completed_at", "TIMESTAMP", "nullable"),
        ("provisioning_status", "VARCHAR", "nullable"),
        ("provisioning_error", "VARCHAR", "nullable"),
        ("created_at / updated_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], proj_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>project_requests</b> (14 colunas)", styles['SubsubTitle']))
    pr_cols = [
        ("id", "UUID", "PK"),
        ("gp_id", "UUID", "FK → users"),
        ("project_name / project_slug", "VARCHAR", "NOT NULL"),
        ("description", "TEXT", "nullable"),
        ("schema_name", "VARCHAR", "nullable"),
        ("status", "ENUM", "PENDING, APPROVED, REJECTED, ACTIVE"),
        ("approved_by", "UUID", "FK → users, nullable"),
        ("approved_at", "TIMESTAMP", "nullable"),
        ("rejection_reason", "TEXT", "nullable"),
        ("initial_password_hash", "VARCHAR", "nullable"),
        ("password_changed", "BOOLEAN", "nullable"),
        ("requested_at / created_at / updated_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], pr_cols, cw))

    story.append(PageBreak())

    # --- Security Tables ---
    story.append(Paragraph("<b>7.2 Tabelas de Segurança</b>", styles['SubsectionTitle']))

    story.append(Paragraph("<b>access_attempts</b> (7 colunas)", styles['SubsubTitle']))
    aa_cols = [
        ("id", "UUID", "PK"),
        ("user_id", "UUID", "FK → users"),
        ("project_id", "UUID", "FK → projects"),
        ("attempt_number", "INTEGER", "nullable"),
        ("blocked", "BOOLEAN", "nullable"),
        ("blocked_at / unblocked_at", "TIMESTAMP", "nullable"),
        ("created_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], aa_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>reset_tokens</b> (7 colunas)", styles['SubsubTitle']))
    rt_cols = [
        ("id", "UUID", "PK"),
        ("user_id", "UUID", "FK → users"),
        ("token", "VARCHAR", "NOT NULL"),
        ("expires_at", "TIMESTAMP", "NOT NULL"),
        ("used", "BOOLEAN", "nullable"),
        ("used_at", "TIMESTAMP", "nullable"),
        ("created_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], rt_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>team_invites</b> (12 colunas)", styles['SubsubTitle']))
    ti_cols = [
        ("id", "UUID", "PK"),
        ("project_id", "UUID", "FK → projects"),
        ("email", "VARCHAR", "NOT NULL"),
        ("role", "VARCHAR", "NOT NULL"),
        ("responsibility", "TEXT", "nullable"),
        ("invite_token", "VARCHAR", "token de aceite"),
        ("invite_sent_at / invite_expires_at", "TIMESTAMP", "nullable"),
        ("accepted_at", "TIMESTAMP", "nullable"),
        ("user_id", "UUID", "FK → users, preenchido após aceite"),
        ("is_accepted", "BOOLEAN", "nullable"),
        ("created_at / updated_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], ti_cols, cw))

    story.append(PageBreak())

    # --- Questionnaire & OCG Tables ---
    story.append(Paragraph("<b>7.3 Tabelas de Questionário e OCG</b>", styles['SubsectionTitle']))

    story.append(Paragraph("<b>questionnaires</b> (14 colunas)", styles['SubsubTitle']))
    q_cols = [
        ("id", "UUID", "PK"),
        ("project_id", "UUID", "FK → projects"),
        ("gp_email", "VARCHAR", "NOT NULL"),
        ("responses", "VARCHAR/JSON", "respostas do questionário"),
        ("adherence_score", "INTEGER", "nullable"),
        ("status", "VARCHAR", "draft, submitted, analyzed, approved, rejected"),
        ("approved", "BOOLEAN", "nullable"),
        ("validations", "VARCHAR", "nullable"),
        ("observations / restrictions", "VARCHAR", "nullable"),
        ("highlighted_fields", "VARCHAR", "nullable"),
        ("submitted_at / analyzed_at", "TIMESTAMP", "nullable"),
        ("created_at / updated_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], q_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>ocg</b> (14 colunas)", styles['SubsubTitle']))
    ocg_cols = [
        ("id", "UUID", "PK"),
        ("questionnaire_id", "UUID", "UNIQUE, FK → questionnaires"),
        ("project_id", "UUID", "FK → projects"),
        ("p1 a p7_score", "FLOAT", "Score de cada pilar (0-100)"),
        ("overall_score", "FLOAT", "Score composto final"),
        ("status", "VARCHAR", "READY, NEEDS_REVIEW, AT_RISK, BLOCKED"),
        ("is_blocking", "BOOLEAN", "true se P7 < 70"),
        ("ocg_data", "JSON", "OCG completo em JSON"),
        ("generated_at / generated_by", "TIMESTAMP/UUID", "metadata"),
        ("reviewed_at / reviewed_by", "TIMESTAMP/UUID", "nullable"),
        ("created_at / updated_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], ocg_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>ocg_analysis_log</b> (7 colunas)", styles['SubsubTitle']))
    oal_cols = [
        ("id", "UUID", "PK"),
        ("ocg_id", "UUID", "FK → ocg"),
        ("agent_name", "VARCHAR", "Nome do agente (Agent 0-8)"),
        ("input_hash / output_hash", "VARCHAR", "Hashes para auditoria"),
        ("tokens_used", "INTEGER", "Tokens consumidos"),
        ("latency_ms", "INTEGER", "Latência em milissegundos"),
        ("created_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], oal_cols, cw))

    story.append(PageBreak())

    # --- Audit & Support Tables ---
    story.append(Paragraph("<b>7.4 Tabelas de Auditoria e Suporte</b>", styles['SubsectionTitle']))

    story.append(Paragraph("<b>audit_log_global</b> (9 colunas)", styles['SubsubTitle']))
    alg_cols = [
        ("id", "UUID", "PK"),
        ("event_type", "VARCHAR", "tipo do evento"),
        ("actor_id / actor_email", "UUID / VARCHAR", "quem executou"),
        ("resource_type", "VARCHAR", "tipo do recurso"),
        ("resource_id", "UUID", "nullable"),
        ("details", "VARCHAR/JSON", "nullable"),
        ("previous_hash", "VARCHAR", "hash do registro anterior (cadeia)"),
        ("created_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], alg_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>support_tickets</b> (12 colunas)", styles['SubsubTitle']))
    st_cols = [
        ("id", "UUID", "PK"),
        ("user_id / project_id", "UUID", "FK → users / projects"),
        ("title / description", "VARCHAR", "NOT NULL"),
        ("error_message / erratic_behavior", "VARCHAR", "nullable"),
        ("severity", "VARCHAR", "LOW, MEDIUM, HIGH, CRITICAL"),
        ("status", "VARCHAR", "OPEN, IN_PROGRESS, RESOLVED, CLOSED"),
        ("created_at / first_response_at", "TIMESTAMP", "auto / nullable"),
        ("resolved_at / updated_at", "TIMESTAMP", "nullable / auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], st_cols, cw))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>system_alerts</b> (12 colunas)", styles['SubsubTitle']))
    sa_cols = [
        ("id", "UUID", "PK"),
        ("alert_type / severity", "VARCHAR", "tipo e severidade"),
        ("title / message", "VARCHAR", "NOT NULL"),
        ("details", "VARCHAR", "nullable"),
        ("sent_to_teams / sent_to_slack / sent_via_email", "BOOLEAN", "nullable"),
        ("status", "VARCHAR", "PENDING, SENT, ACKNOWLEDGED"),
        ("acknowledged_at / acknowledged_by", "TIMESTAMP/UUID", "nullable"),
        ("created_at / sent_at", "TIMESTAMP", "auto"),
    ]
    story.append(make_table(["Coluna", "Tipo", "Restrições"], sa_cols, cw))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "<b>Outras tabelas:</b> artifacts (12 col), artifact_evaluations (18 col), "
        "onboarding_progress (30 col), project_members (7 col), organization_members (4 col), "
        "pillar_templates (8 col), pillar_configuration (9 col), company_policies (7 col), "
        "stack_cache (8 col), ogc_versions (11 col), integration_webhooks, piloter_queries, piloter_quota_history.",
        styles['BodyText2']))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 8. ENDPOINTS DA API (60+)
    # --------------------------------------------------------
    story.append(Paragraph("8. Endpoints da API (60+)", styles['SectionTitle']))
    story.append(Paragraph(
        "Todos os endpoints estão prefixados com /api/v1/. Autenticação via JWT Bearer Token.",
        styles['BodyText2']))

    # Auth
    story.append(Paragraph("<b>8.1 Auth (12 endpoints)</b>", styles['SubsectionTitle']))
    auth_eps = [
        ("POST", "/auth/bootstrap-admin", "Público", "Criar primeiro admin (só se DB vazio)"),
        ("POST", "/auth/login", "Público", "Login com email/senha → JWT tokens"),
        ("GET", "/auth/me", "Bearer", "Dados do usuário autenticado"),
        ("POST", "/auth/refresh", "Público", "Renovar access_token via refresh_token"),
        ("POST", "/auth/change-password", "Bearer", "Alterar senha (requer senha atual)"),
        ("POST", "/auth/reset-password", "Público", "Solicitar reset por email"),
        ("POST", "/auth/reset-password-confirm", "Público", "Confirmar nova senha com token"),
        ("POST", "/auth/first-access", "Bearer", "Definir senha no primeiro acesso"),
        ("POST", "/auth/logout", "Bearer", "Invalidar token atual"),
        ("GET", "/auth/validate-token/{token}", "Público", "Validar token de convite"),
        ("POST", "/auth/accept-invite", "Público", "Aceitar convite e criar conta"),
        ("GET", "/auth/check-invite/{token}", "Público", "Verificar status do convite"),
    ]
    cw_ep = [avail_w * 0.07, avail_w * 0.30, avail_w * 0.10, avail_w * 0.53]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], auth_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # Projects
    story.append(Paragraph("<b>8.2 Projects (4 endpoints)</b>", styles['SubsectionTitle']))
    proj_eps = [
        ("GET", "/projects/", "Bearer", "Listar projetos (Admin=todos, GP=seus)"),
        ("POST", "/projects/", "Bearer", "Criar novo projeto"),
        ("GET", "/projects/{id}", "Bearer", "Detalhe de um projeto"),
        ("PUT", "/projects/{id}", "Bearer", "Atualizar projeto"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], proj_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # Questionnaires
    story.append(Paragraph("<b>8.3 Questionnaires (5 endpoints)</b>", styles['SubsectionTitle']))
    q_eps = [
        ("GET", "/questionnaires/", "Bearer", "Listar questionários do projeto"),
        ("POST", "/questionnaires/", "Bearer", "Criar/submeter questionário"),
        ("GET", "/questionnaires/{id}", "Bearer", "Detalhe do questionário"),
        ("PUT", "/questionnaires/{id}", "Bearer", "Atualizar questionário (draft)"),
        ("POST", "/questionnaires/{id}/submit", "Bearer", "Submeter para análise"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], q_eps, cw_ep))

    story.append(PageBreak())

    # Admin
    story.append(Paragraph("<b>8.4 Admin (16 endpoints)</b>", styles['SubsectionTitle']))
    admin_eps = [
        ("GET", "/admin/users", "Admin", "Listar todos os usuários"),
        ("POST", "/admin/users", "Admin", "Criar novo usuário"),
        ("PUT", "/admin/users/{id}", "Admin", "Atualizar usuário"),
        ("DELETE", "/admin/users/{id}", "Admin", "Desativar usuário (não pode ser self)"),
        ("POST", "/admin/invite-admin", "Admin", "Convidar novo admin com senha temporária"),
        ("POST", "/admin/projects", "Admin", "Criar projeto via admin"),
        ("GET", "/admin/projects/pending", "Admin", "Listar projetos pendentes"),
        ("POST", "/admin/projects/{id}/approve", "Admin", "Aprovar projeto"),
        ("POST", "/admin/projects/{id}/reject", "Admin", "Rejeitar projeto (com motivo)"),
        ("GET", "/admin/external-requests", "Admin", "Listar requisições externas"),
        ("GET", "/admin/external-requests/{id}", "Admin", "Detalhe da requisição externa"),
        ("POST", "/admin/external-requests/generate-link", "Admin", "Gerar link de questionário (5d)"),
        ("POST", "/admin/external-requests/{id}/approve", "Admin", "Aprovar requisição externa"),
        ("POST", "/admin/external-requests/{id}/reject", "Admin", "Rejeitar requisição externa"),
        ("GET", "/admin/dashboard/metrics", "Admin", "Métricas do dashboard"),
        ("GET", "/admin/audit-log", "Admin", "Consultar log de auditoria"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], admin_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # Agents
    story.append(Paragraph("<b>8.5 Agents (4 endpoints)</b>", styles['SubsectionTitle']))
    ag_eps = [
        ("POST", "/agents/analyze", "Bearer", "Iniciar análise do questionário (async)"),
        ("GET", "/agents/status/{job_id}", "Bearer", "Status da análise (progresso por agente)"),
        ("GET", "/agents/result/{job_id}", "Bearer", "Resultado final da análise"),
        ("POST", "/agents/retry/{job_id}", "Bearer", "Re-executar análise falhada"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], ag_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # Evaluation
    story.append(Paragraph("<b>8.6 Evaluation (4 endpoints)</b>", styles['SubsectionTitle']))
    ev_eps = [
        ("POST", "/evaluation/artifacts/{id}/evaluate", "Bearer", "Avaliar artefato (7 pilares)"),
        ("GET", "/evaluation/artifacts/{id}/scores", "Bearer", "Scores do artefato"),
        ("GET", "/evaluation/artifacts/{id}/history", "Bearer", "Histórico de avaliações"),
        ("POST", "/evaluation/artifacts/{id}/approve", "Admin", "Aprovar artefato para CodeGen"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], ev_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # CodeGen
    story.append(Paragraph("<b>8.7 Code Generation (4 endpoints)</b>", styles['SubsectionTitle']))
    cg_eps = [
        ("POST", "/codegen/generate", "Bearer", "Iniciar geração de código a partir do OCG"),
        ("GET", "/codegen/status/{job_id}", "Bearer", "Status da geração"),
        ("GET", "/codegen/result/{job_id}", "Bearer", "Código gerado (download)"),
        ("POST", "/codegen/preview", "Bearer", "Preview da estrutura antes de gerar"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], cg_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # Webhooks
    story.append(Paragraph("<b>8.8 Webhooks (3 endpoints)</b>", styles['SubsectionTitle']))
    wh_eps = [
        ("POST", "/webhooks/questionnaire", "Webhook", "Receber questionário do n8n"),
        ("POST", "/webhooks/questionnaire-result", "Webhook", "Callback resultado da análise"),
        ("POST", "/webhooks/external-project-result", "Webhook", "Callback validação projeto externo"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], wh_eps, cw_ep))
    story.append(Spacer(1, 0.3 * cm))

    # Dashboard
    story.append(Paragraph("<b>8.9 Dashboard (7 endpoints)</b>", styles['SubsectionTitle']))
    db_eps = [
        ("GET", "/dashboard/summary", "Bearer", "Resumo geral (projetos, usuários, OCGs)"),
        ("GET", "/dashboard/projects/stats", "Bearer", "Estatísticas de projetos"),
        ("GET", "/dashboard/ocg/stats", "Bearer", "Estatísticas de OCGs gerados"),
        ("GET", "/dashboard/agents/stats", "Bearer", "Performance dos agentes IA"),
        ("GET", "/dashboard/recent-activity", "Bearer", "Atividades recentes"),
        ("GET", "/dashboard/alerts", "Bearer", "Alertas pendentes"),
        ("GET", "/dashboard/health", "Público", "Health check do sistema"),
    ]
    story.append(make_table(["Método", "Path", "Auth", "Descrição"], db_eps, cw_ep))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 9. QUESTIONÁRIO TÉCNICO (54 CAMPOS)
    # --------------------------------------------------------
    story.append(Paragraph("9. Questionário Técnico (54 Campos)", styles['SectionTitle']))
    story.append(Paragraph(
        "O questionário possui 49 perguntas respondidas pelo GP e 5 perguntas preenchidas pela IA, "
        "organizadas em 8 seções (blocos A.1 a A.12), cada uma mapeada nos 7 pilares.",
        styles['BodyText2']))

    q_fields = [
        ("Q01", "Nome do Projeto", "text", "A.1", "P1"),
        ("Q02", "Descrição do Projeto", "text", "A.1", "P1"),
        ("Q03", "Objetivo Principal", "text", "A.1", "P1"),
        ("Q04", "Público-Alvo", "text", "A.1", "P1, P3"),
        ("Q05", "Expectativa de ROI", "text", "A.1", "P1"),
        ("Q06", "Prazo Estimado (meses)", "single", "A.2", "P1"),
        ("Q07", "Orçamento Disponível", "single", "A.2", "P1"),
        ("Q08", "Tamanho da Equipe", "single", "A.2", "P1, P5"),
        ("Q09", "Regulações Aplicáveis", "multi", "A.3", "P2"),
        ("Q10", "LGPD Obrigatório?", "single", "A.3", "P2, P7"),
        ("Q11", "GDPR Obrigatório?", "single", "A.3", "P2, P7"),
        ("Q12", "Residência de Dados", "single", "A.3", "P2"),
        ("Q13", "Certificações Necessárias", "multi", "A.3", "P2"),
        ("Q14", "Auditoria Requerida?", "single", "A.3", "P2"),
        ("Q15", "Políticas Internas Aplicáveis", "text", "A.3", "P2"),
        ("Q16", "Funcionalidades Core (MVP)", "text", "A.4", "P3"),
        ("Q17", "User Stories Principais", "text", "A.4", "P3"),
        ("Q18", "Integrações com Sistemas Existentes", "multi", "A.4", "P3, P5"),
        ("Q19", "APIs de Terceiros", "text", "A.4", "P3"),
        ("Q20", "Fluxos de Trabalho Principais", "text", "A.4", "P3"),
        ("Q21", "Módulos do Sistema", "text", "A.5", "P3"),
        ("Q22", "Notificações Necessárias", "multi", "A.5", "P3"),
        ("Q23", "Relatórios e Dashboards", "text", "A.5", "P3"),
        ("Q24", "Importação/Exportação de Dados", "multi", "A.5", "P3, P6"),
        ("Q25", "Multi-idioma Necessário?", "single", "A.5", "P3"),
        ("Q26", "Tempo de Resposta Esperado (ms)", "single", "A.6", "P4"),
        ("Q27", "Usuários Concorrentes Estimados", "single", "A.6", "P4, P5"),
        ("Q28", "SLA de Disponibilidade", "single", "A.6", "P4"),
        ("Q29", "Volume de Dados Esperado", "single", "A.6", "P4, P6"),
        ("Q30", "Pico de Carga Estimado", "text", "A.6", "P4"),
        ("Q31", "Necessidade de Cache?", "single", "A.7", "P4, P5"),
        ("Q32", "CDN Necessário?", "single", "A.7", "P4"),
        ("Q33", "Tipo de Arquitetura Preferida", "single", "A.8", "P5"),
        ("Q34", "Padrões de Design Preferidos", "multi", "A.8", "P5"),
        ("Q35", "Modelo de Deploy", "single", "A.8", "P5"),
        ("Q36", "Cloud Provider Preferido", "single", "A.8", "P5"),
        ("Q37", "Containerização?", "single", "A.8", "P5"),
        ("Q38", "CI/CD Necessário?", "single", "A.8", "P5"),
        ("Q39", "Tipo de Banco de Dados", "single", "A.9", "P6"),
        ("Q40", "Modelo de Dados Esperado", "text", "A.9", "P6"),
        ("Q41", "Estratégia de Backup", "single", "A.9", "P6"),
        ("Q42", "Taxa de Crescimento de Dados", "single", "A.9", "P6"),
        ("Q43", "Método de Autenticação", "multi", "A.10", "P7"),
        ("Q44", "Criptografia Necessária", "multi", "A.10", "P7"),
        ("Q45", "Scan de Vulnerabilidades?", "single", "A.10", "P7"),
        ("Q46", "Plano de Resposta a Incidentes?", "single", "A.10", "P7"),
        ("Q47", "Tipo de Output", "single", "A.11", "P5"),
        ("Q48", "Linguagens Preferidas (Backend)", "multi", "A.11", "P5"),
        ("Q49", "Framework Frontend Preferido", "single", "A.11", "P5, P3"),
        ("Q50", "IA: Análise de Maturidade", "auto", "A.12", "P1-P7"),
        ("Q51", "IA: Gaps Detectados", "auto", "A.12", "P1-P7"),
        ("Q52", "IA: Conflitos Identificados", "auto", "A.12", "P1-P7"),
        ("Q53", "IA: Riscos Técnicos", "auto", "A.12", "P4-P7"),
        ("Q54", "IA: Recomendações", "auto", "A.12", "P1-P7"),
    ]
    cw_q = [avail_w * 0.06, avail_w * 0.30, avail_w * 0.08, avail_w * 0.08, avail_w * 0.48]
    # Split into two pages for readability
    story.append(make_table(["Q#", "Campo", "Tipo", "Bloco", "Pilar"], q_fields[:27], cw_q))
    story.append(PageBreak())
    story.append(Paragraph("9. Questionário Técnico (continuação)", styles['SectionTitle']))
    story.append(make_table(["Q#", "Campo", "Tipo", "Bloco", "Pilar"], q_fields[27:], cw_q))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 10. PIPELINE DE VERIFICAÇÃO TECNOLÓGICA
    # --------------------------------------------------------
    story.append(Paragraph("10. Pipeline de Verificação Tecnológica", styles['SectionTitle']))

    story.append(Paragraph("<b>8 Fases de Verificação</b>", styles['SubsectionTitle']))
    pipe_data = [
        ("Fase 1", "Validação de Entrada", "Verificação de campos obrigatórios, tipos e formatos."),
        ("Fase 2", "Compatibilidade de Stack", "Verifica se as tecnologias escolhidas são compatíveis entre si."),
        ("Fase 3", "Verificação de Requisitos", "Valida se os requisitos funcionais e não funcionais são consistentes."),
        ("Fase 4", "Análise de Segurança", "Verifica conformidade com padrões de segurança (OWASP, LGPD, GDPR)."),
        ("Fase 5", "Validação Arquitetural", "Verifica se a arquitetura suporta os requisitos de performance e escala."),
        ("Fase 6", "Análise de Dados", "Valida modelo de dados, estratégia de backup e crescimento."),
        ("Fase 7", "Verificação de Integrações", "Valida APIs de terceiros, webhooks e conectores necessários."),
        ("Fase 8", "Consolidação e Parecer", "Gera parecer final: APROVADO ou DEVOLVIDO com ações corretivas."),
    ]
    cw_p = [avail_w * 0.10, avail_w * 0.22, avail_w * 0.68]
    story.append(make_table(["Fase", "Nome", "Descrição"], pipe_data, cw_p))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Severidades</b>", styles['SubsectionTitle']))
    sev_data = [
        ("BLOCKER", "Impede prosseguimento. Deve ser corrigido antes de continuar.", "Vermelho"),
        ("CRITICAL", "Problema grave que pode comprometer a qualidade. Correção urgente.", "Laranja"),
        ("WARNING", "Alerta de possível problema. Correção recomendada.", "Amarelo"),
        ("INFO", "Informação relevante. Não requer ação imediata.", "Azul"),
    ]
    cw_s = [avail_w * 0.14, avail_w * 0.70, avail_w * 0.16]
    story.append(make_table(["Severidade", "Descrição", "Cor"], sev_data, cw_s))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>8 Matrizes de Compatibilidade</b>", styles['SubsectionTitle']))
    matrix_data = [
        ("M1", "Backend × Frontend", "Compatibilidade entre linguagem backend e framework frontend"),
        ("M2", "Backend × Banco de Dados", "Compatibilidade entre ORM/driver e banco escolhido"),
        ("M3", "Frontend × Infra", "Compatibilidade entre framework frontend e modelo de deploy"),
        ("M4", "Stack × Performance", "Stack atende requisitos de performance (SLA, latência)"),
        ("M5", "Stack × Segurança", "Stack atende requisitos de segurança (criptografia, auth)"),
        ("M6", "Stack × Escalabilidade", "Stack suporta crescimento projetado"),
        ("M7", "Integrações × APIs", "APIs de terceiros compatíveis com stack escolhida"),
        ("M8", "Cloud × Containerização", "Cloud provider compatível com modelo de containerização"),
    ]
    cw_m = [avail_w * 0.06, avail_w * 0.24, avail_w * 0.70]
    story.append(make_table(["ID", "Matriz", "Descrição"], matrix_data, cw_m))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 11. ARQUITETURA DE AGENTES IA
    # --------------------------------------------------------
    story.append(Paragraph("11. Arquitetura de Agentes IA (8 Agentes)", styles['SectionTitle']))
    story.append(Paragraph(
        "O GCA utiliza um sistema de 8 agentes IA especializados para analisar o questionário e "
        "gerar o OCG (Objeto Contexto Global). O Agent 0 (Analyzer) classifica as respostas por pilar, "
        "os Agents 1-7 (Pillar Specialists) analisam em paralelo, e o Agent 8 (Consolidator) "
        "produz o OCG final. Todos utilizam Claude Opus 4.6 via Anthropic SDK.",
        styles['BodyText2']))

    story.append(Paragraph("<b>Agentes</b>", styles['SubsectionTitle']))
    agent_data = [
        ("Agent 0", "Analyzer", "Claude Opus 4.6",
         "Classifica respostas por pilar, detecta anomalias, extrai metadados do projeto."),
        ("Agent 1", "P1 — Business", "Claude Opus 4.6",
         "Avalia contexto de negócio, ROI, alinhamento estratégico. Q1-Q8."),
        ("Agent 2", "P2 — Rules", "Claude Opus 4.6",
         "Avalia conformidade regulatória, LGPD, GDPR, certificações. Q9-Q15."),
        ("Agent 3", "P3 — Features", "Claude Opus 4.6",
         "Avalia completude funcional, MVP, user stories, integrações. Q16-Q25."),
        ("Agent 4", "P4 — NFR", "Claude Opus 4.6",
         "Avalia performance, escalabilidade, disponibilidade, SLA. Q26-Q32."),
        ("Agent 5", "P5 — Architecture", "Claude Opus 4.6",
         "Avalia design do sistema, padrões, modularidade, stack. Q33-Q38."),
        ("Agent 6", "P6 — Data", "Claude Opus 4.6",
         "Avalia modelo de dados, armazenamento, migrações, backup. Q39-Q42."),
        ("Agent 7", "P7 — Security", "Claude Opus 4.6",
         "Avalia segurança: auth, criptografia, vulnerabilidades. BLOQUEANTE se < 70. Q43-Q46."),
        ("Agent 8", "Consolidator", "Claude Opus 4.6",
         "Recebe outputs dos 7 especialistas, balanceia trade-offs, produz OCG final."),
    ]
    cw_a = [avail_w * 0.08, avail_w * 0.14, avail_w * 0.14, avail_w * 0.64]
    story.append(make_table(["Agente", "Nome", "Modelo", "Responsabilidade"], agent_data, cw_a))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Regras de Score</b>", styles['SubsectionTitle']))
    score_data = [
        ("90-100", "Excelente", "Maturidade completa, todos os aspectos cobertos.", "READY"),
        ("70-89", "Bom", "Gaps menores a endereçar, pode prosseguir.", "READY / NEEDS_REVIEW"),
        ("50-69", "Regular", "Gaps significativos, revisão necessária.", "AT_RISK"),
        ("< 50", "Crítico", "Problemas graves, deve endereçar antes de prosseguir.", "BLOCKED"),
    ]
    cw_sc = [avail_w * 0.10, avail_w * 0.12, avail_w * 0.52, avail_w * 0.26]
    story.append(make_table(["Score", "Nível", "Descrição", "Status OCG"], score_data, cw_sc))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "<b>Regra P7 Bloqueante:</b> Se o score do Pilar 7 (Segurança) for inferior a 70, "
        "o OCG recebe status BLOCKED e code_generation_allowed=false. O projeto não pode "
        "prosseguir para geração de código até que os problemas de segurança sejam resolvidos.",
        styles['BodyText2']))

    story.append(PageBreak())

    # Pipeline diagram for agents
    story.append(Paragraph("<b>Pipeline dos Agentes IA</b>", styles['SubsectionTitle']))
    story.append(ParallelFlowDiagram(
        "Pipeline: Questionário → OCG",
        top_boxes=[
            ("Questionário (54 campos)\nSubmetido via link externo ou formulário", "dark"),
            ("Agent 0: Analyzer\nClassifica respostas por pilar, detecta anomalias", "violet"),
        ],
        parallel_groups=[
            [
                ("Agent 1\nP1 Business", "blue"),
                ("Agent 2\nP2 Rules", "blue"),
                ("Agent 3\nP3 Features", "blue"),
                ("Agent 4\nP4 NFR", "blue"),
            ],
            [
                ("Agent 5\nP5 Architecture", "blue"),
                ("Agent 6\nP6 Data", "blue"),
                ("Agent 7\nP7 Security", "red"),
            ],
        ],
        bottom_boxes=[
            ("Agent 8: Consolidator\nBalanceia trade-offs, produz OCG final", "violet"),
            ("OCG Gerado\nSalvo no DB, enviado ao Admin", "emerald"),
        ],
    ))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 12. DIAGRAMAS DE FLUXO
    # --------------------------------------------------------
    story.append(Paragraph("12. Diagramas de Fluxo", styles['SectionTitle']))
    story.append(Paragraph(
        "Todos os diagramas são apresentados em orientação Top-Down (TD), "
        "com largura máxima ajustada ao formato A4.",
        styles['BodyText2']))

    # Diagram 1: Login e Autenticação
    story.append(PageBreak())
    story.append(FlowDiagram(
        "Fluxo 1: Login e Autenticação",
        [
            ("Usuário acessa\ngca.code-auditor.com.br", "dark"),
            ("Tela de Login\nEmail + Senha", "violet"),
            ("POST /api/v1/auth/login\nValidação de credenciais", "blue"),
            ("first_access_completed?\nVerifica flag no DB", "amber"),
            ("Modal FirstAccess\nDefinir senha permanente", "red"),
            ("Dashboard\nAcesso ao sistema", "emerald"),
        ],
        ["", "", "", "false → Modal / true → Dashboard", "Senha definida", ""],
    ))

    # Diagram 2: Convite de Usuário
    story.append(PageBreak())
    story.append(FlowDiagram(
        "Fluxo 2: Convite de Usuário (RF-001)",
        [
            ("Admin acessa\nAdminUsersPage", "violet"),
            ("Admin preenche convite\nEmail, role, projeto", "violet"),
            ("POST /api/v1/admin/invite-admin\nCria team_invite + senha temporária", "blue"),
            ("EmailService envia\nLink + senha temporária (7 dias)", "amber"),
            ("Convidado clica no link\nValidação do token", "dark"),
            ("Convidado cria conta\nAceita convite, define senha", "emerald"),
            ("team_invites.accepted_at\nuser_id preenchido", "emerald"),
        ],
        ["", "", "", "Email enviado", "", "Conta criada", ""],
    ))

    # Diagram 3: Questionário → Verificação → OCG
    story.append(PageBreak())
    story.append(FlowDiagram(
        "Fluxo 3: Questionário → Verificação → OCG",
        [
            ("GP preenche questionário\n54 campos, 8 seções", "dark"),
            ("Submit → POST /api/v1/questionnaires\nSalva no DB com status 'submitted'", "blue"),
            ("Pipeline de Verificação\n8 fases, 8 matrizes de compatibilidade", "amber"),
            ("Resultado: APROVADO?\nSeveridades: BLOCKER → INFO", "amber"),
            ("Agentes IA (8 agentes)\nAnálise paralela por pilar", "violet"),
            ("OCG Gerado\nScores, stack, compliance, riscos", "emerald"),
            ("Admin revisa OCG\nAprova ou solicita revisão", "violet"),
        ],
        ["", "", "", "Sim → Agentes / Não → Devolvido", "", "", ""],
    ))

    # Diagram 4: Criação de Projeto Externo
    story.append(PageBreak())
    story.append(FlowDiagram(
        "Fluxo 4: Criação de Projeto Externo",
        [
            ("Admin gera link\nPOST /admin/external-requests/generate-link", "violet"),
            ("Link com token (5 dias)\nEnviado por email ao GP externo", "amber"),
            ("GP acessa /novo-projeto?token=xxx\nPreenche 46 perguntas em 8 seções", "dark"),
            ("Submit → Número REQ-YYYYMMDD-XXXXX\nSalva no DB, trigger n8n async", "blue"),
            ("n8n + IA analisa\nGaps, conflitos, riscos, recomendações", "violet"),
            ("Admin revisa análise IA\n/admin/external-requests/{id}", "violet"),
            ("Aprovação → Projeto criado\nOrganização + membros + email", "emerald"),
        ],
        ["", "email", "", "", "webhook callback", "", ""],
    ))

    # Diagram 5: Aprovação/Rejeição de Projeto
    story.append(PageBreak())
    story.append(FlowDiagram(
        "Fluxo 5: Aprovação / Rejeição de Projeto",
        [
            ("Requisição de projeto\nStatus: PENDING", "dark"),
            ("Admin acessa lista\nGET /admin/projects/pending", "violet"),
            ("Admin visualiza detalhes\nAnálise IA, questionário, dados do GP", "violet"),
            ("Decisão do Admin\nAprovar ou Rejeitar", "amber"),
            ("APROVADO: Projeto criado\nStatus: ACTIVE, organização, membros", "emerald"),
            ("REJEITADO: Motivo registrado\nEmail ao GP com rejection_reason", "red"),
        ],
        ["", "", "", "Decisão", "", ""],
    ))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 13. DIAGRAMAS DE SEQUÊNCIA
    # --------------------------------------------------------
    story.append(Paragraph("13. Diagramas de Sequência", styles['SectionTitle']))

    # Sequence 1: Login Completo
    story.append(PageBreak())
    story.append(SequenceDiagram(
        "Sequência 1: Login Completo",
        [("User", "dark"), ("Frontend", "violet"), ("API", "blue"), ("PostgreSQL", "emerald")],
        [
            (0, 1, "Acessa gca.code-auditor.com.br", False),
            (1, 0, "Exibe LoginPage", True),
            (0, 1, "Submete email + senha", False),
            (1, 2, "POST /auth/login", False),
            (2, 3, "SELECT * FROM users WHERE email=...", False),
            (3, 2, "User record", True),
            (2, 2, "Verifica bcrypt hash", False),
            (2, 1, "JWT access_token + refresh_token", True),
            (1, 1, "Verifica first_access_completed", False),
            (1, 0, "Dashboard ou FirstAccessModal", True),
        ],
    ))

    # Sequence 2: Convite de Usuário
    story.append(PageBreak())
    story.append(SequenceDiagram(
        "Sequência 2: Convite de Usuário",
        [("Admin", "violet"), ("API", "blue"), ("PostgreSQL", "emerald"),
         ("EmailSvc", "amber"), ("Convidado", "dark")],
        [
            (0, 1, "POST /admin/invite-admin", False),
            (1, 2, "INSERT team_invites", False),
            (2, 1, "OK (invite_token)", True),
            (1, 3, "send_invitation_email()", False),
            (3, 4, "Email: link + senha temporária", False),
            (4, 1, "GET /auth/validate-token/{token}", False),
            (1, 2, "SELECT * FROM team_invites", False),
            (2, 1, "Invite válido (não expirado)", True),
            (1, 4, "Formulário de aceite", True),
            (4, 1, "POST /auth/accept-invite", False),
            (1, 2, "INSERT users + UPDATE team_invites", False),
            (1, 4, "Conta criada, redireciona login", True),
        ],
    ))

    # Sequence 3: Questionário → OCG
    story.append(PageBreak())
    story.append(SequenceDiagram(
        "Sequência 3: Questionário → OCG",
        [("GP", "dark"), ("Frontend", "violet"), ("API", "blue"),
         ("TechVerif", "amber"), ("AgentsIA", "red"), ("PostgreSQL", "emerald")],
        [
            (0, 1, "Preenche 54 campos", False),
            (1, 2, "POST /questionnaires", False),
            (2, 5, "INSERT questionnaires", False),
            (2, 3, "Inicia verificação (8 fases)", False),
            (3, 2, "Resultado: APROVADO", True),
            (2, 4, "POST /agents/analyze (async)", False),
            (4, 4, "Agent 0: Analyzer", False),
            (4, 4, "Agents 1-7: paralelo", False),
            (4, 4, "Agent 8: Consolidator", False),
            (4, 2, "OCG completo (JSON)", True),
            (2, 5, "INSERT ocg + ocg_analysis_log", False),
            (2, 1, "OCG gerado com sucesso", True),
        ],
    ))

    # Sequence 4: Reset de Senha
    story.append(PageBreak())
    story.append(SequenceDiagram(
        "Sequência 4: Reset de Senha",
        [("User", "dark"), ("Frontend", "violet"), ("API", "blue"),
         ("PostgreSQL", "emerald"), ("EmailSvc", "amber")],
        [
            (0, 1, "Clica 'Esqueci minha senha'", False),
            (1, 2, "POST /auth/reset-password", False),
            (2, 3, "INSERT reset_tokens (expira 1h)", False),
            (2, 4, "send_password_reset_email()", False),
            (4, 0, "Email com link de reset", False),
            (0, 1, "Clica link, define nova senha", False),
            (1, 2, "POST /auth/reset-password-confirm", False),
            (2, 3, "Valida token, UPDATE users.password_hash", False),
            (3, 2, "OK", True),
            (2, 1, "Senha alterada com sucesso", True),
            (1, 0, "Redireciona para LoginPage", True),
        ],
    ))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 14. DIAGRAMAS DE ESTADO
    # --------------------------------------------------------
    story.append(Paragraph("14. Diagramas de Estado", styles['SectionTitle']))

    # State 1: Projeto
    story.append(StateDiagram(
        "Estado do Projeto",
        [
            ("INITIALIZING", "gray"),
            ("WIZARD_STEP_1 (Git Config)", "violet"),
            ("WIZARD_STEP_2 (SMTP Config)", "violet"),
            ("WIZARD_STEP_3 (Team Invites)", "violet"),
            ("WIZARD_STEP_4 (Stack Selection)", "violet"),
            ("ACTIVE", "emerald"),
            ("ARCHIVED", "dark"),
        ],
        ["Criação", "Step 1 completo", "Step 2 completo", "Step 3 completo", "Step 4 completo", "Arquivamento"],
    ))

    story.append(PageBreak())

    # State 2: Questionário
    story.append(StateDiagramBranch(
        "Estado do Questionário",
        [
            ("DRAFT", "gray"),
            ("PENDING (submetido)", "amber"),
            ("ANALYZING (agentes IA)", "violet"),
        ],
        "Resultado da Análise",
        [
            [("APPROVED", "emerald"), ("OCG_GENERATED", "emerald")],
            [("REVISION_NEEDED", "amber"), ("TIMEOUT (5 dias)", "red")],
        ],
    ))

    story.append(PageBreak())

    # State 3: OCG
    story.append(StateDiagramBranch(
        "Estado do OCG",
        [
            ("GENERATING (agentes processando)", "violet"),
        ],
        "Score Final",
        [
            [("READY (score >= 90)", "emerald")],
            [("NEEDS_REVIEW (70-89)", "amber")],
            [("AT_RISK (50-69)", "amber")],
            [("BLOCKED (P7 < 70)", "red")],
        ],
    ))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 15. PIPELINE N8N
    # --------------------------------------------------------
    story.append(Paragraph("15. Pipeline n8n", styles['SectionTitle']))

    story.append(Paragraph(
        "O n8n é o motor de automação de workflows do GCA, rodando como container Docker "
        "na porta 5678. Ele recebe webhooks do backend, executa análises IA e retorna resultados.",
        styles['BodyText2']))

    story.append(Paragraph("<b>Fluxo Principal</b>", styles['SubsectionTitle']))
    n8n_flow = [
        ("Trigger", "Webhook POST /webhooks/questionnaire", "Recebe dados do questionário submetido"),
        ("Parse", "Function: Extract Data", "Extrai e normaliza dados do questionário"),
        ("IA", "HTTP: Qwen/Haiku Analysis", "Envia para modelo IA (gaps, conflitos, riscos)"),
        ("Process", "Function: Parse AI Output", "Processa resposta da IA em formato estruturado"),
        ("Callback", "HTTP: POST /webhooks/questionnaire-result", "Retorna resultado ao backend GCA"),
        ("DB", "Backend atualiza DB", "Questionnaire.n8n_validation_result = análise"),
    ]
    cw_n = [avail_w * 0.10, avail_w * 0.32, avail_w * 0.58]
    story.append(make_table(["Etapa", "Node n8n", "Descrição"], n8n_flow, cw_n))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Configuração</b>", styles['SubsectionTitle']))
    n8n_config = [
        ("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/external-project", "URL do webhook trigger"),
        ("N8N_API_URL", "http://n8n:5678/api/v1", "URL da API do n8n"),
        ("N8N_HOST", "n8n.code-auditor.com.br", "URL pública do painel n8n"),
        ("WEBHOOK_SECRET", "***", "Secret para validação HMAC"),
    ]
    cw_nc = [avail_w * 0.25, avail_w * 0.40, avail_w * 0.35]
    story.append(make_table(["Variável", "Valor", "Descrição"], n8n_config, cw_nc))

    story.append(Spacer(1, 0.4 * cm))
    story.append(FlowDiagram(
        "Pipeline n8n: Questionário → Análise IA",
        [
            ("Webhook Trigger\nPOST /webhook/external-project", "dark"),
            ("Function: Extract Data\nNormaliza questionnaire_data", "violet"),
            ("HTTP: Qwen/Haiku AI\nAnalisa gaps, conflitos, riscos", "blue"),
            ("Function: Parse AI Output\nFormata resultado estruturado", "violet"),
            ("HTTP: Callback ao Backend\nPOST /webhooks/questionnaire-result", "emerald"),
            ("Backend atualiza DB\nn8n_validation_result salvo", "emerald"),
        ],
        None,
    ))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 16. MAPA DE TELAS
    # --------------------------------------------------------
    story.append(Paragraph("16. Mapa de Telas (29 Páginas)", styles['SectionTitle']))

    story.append(Paragraph("<b>Autenticação (4 telas)</b>", styles['SubsectionTitle']))
    auth_screens = [
        ("LoginPage", "/login", "Tela de login (email/senha), link para reset"),
        ("FirstAccessModal", "(modal)", "Modal de primeiro acesso (definir senha permanente)"),
        ("ResetPasswordPage", "/reset-password", "Solicitar reset de senha por email"),
        ("ResetPasswordConfirmPage", "/reset-password/:token", "Confirmar nova senha com token"),
    ]
    cw_t = [avail_w * 0.25, avail_w * 0.25, avail_w * 0.50]
    story.append(make_table(["Componente", "Rota", "Descrição"], auth_screens, cw_t))

    story.append(Paragraph("<b>Projeto (16 telas)</b>", styles['SubsectionTitle']))
    proj_screens = [
        ("DashboardPage", "/dashboard", "Dashboard principal com métricas"),
        ("ProjectListPage", "/projects", "Lista de projetos (filtro por status)"),
        ("ProjectDetailPage", "/projects/:id", "Detalhe do projeto (tabs)"),
        ("ProjectTeamPage", "/projects/:id/team", "Gerenciamento de equipe do projeto"),
        ("OnboardingWizard", "/projects/:id/onboard", "Wizard de 5 passos (Git, SMTP, Team, n8n, Stack)"),
        ("QuestionnairePage", "/projects/:id/questionnaire", "Formulário de 54 campos (8 seções)"),
        ("QuestionnaireStatusPage", "/projects/:id/questionnaire/status", "Status do questionário"),
        ("OCGViewPage", "/projects/:id/ocg", "Visualização do OCG gerado"),
        ("OCGDetailPage", "/projects/:id/ocg/:ocg_id", "Detalhe do OCG (scores, stack, riscos)"),
        ("ArtifactListPage", "/projects/:id/artifacts", "Lista de artefatos do projeto"),
        ("ArtifactDetailPage", "/projects/:id/artifacts/:aid", "Detalhe do artefato (avaliação)"),
        ("CodeGenPage", "/projects/:id/codegen", "Geração de código a partir do OCG"),
        ("ExternalQuestionnairePage", "/novo-projeto", "Questionário externo (link com token, 46 Q)"),
        ("ExternalProjectStatusPage", "/novo-projeto/status", "Status da requisição externa"),
        ("NovoProjetoPage", "/novo-projeto", "Criação de projeto (countdown 5 dias)"),
        ("SupportPage", "/projects/:id/support", "Tickets de suporte do projeto"),
    ]
    story.append(make_table(["Componente", "Rota", "Descrição"], proj_screens, cw_t))

    story.append(PageBreak())

    story.append(Paragraph("<b>Admin (4 telas)</b>", styles['SubsectionTitle']))
    admin_screens = [
        ("AdminDashboardPage", "/admin", "Dashboard admin (métricas, atalhos)"),
        ("AdminUsersPage", "/admin/users", "Gerenciamento de usuários (GPs, admins)"),
        ("AdminProjectsPage", "/admin/projects", "Aprovação/rejeição de projetos"),
        ("AdminExternalRequestsPage", "/admin/external-requests", "Requisições externas (análise IA)"),
    ]
    story.append(make_table(["Componente", "Rota", "Descrição"], admin_screens, cw_t))

    story.append(Paragraph("<b>Sistema (5 telas)</b>", styles['SubsectionTitle']))
    sys_screens = [
        ("SettingsPage", "/settings", "Configurações do sistema"),
        ("AuditLogPage", "/admin/audit-log", "Log de auditoria (filtros, busca)"),
        ("AlertsPage", "/admin/alerts", "Alertas do sistema"),
        ("ProfilePage", "/profile", "Perfil do usuário logado"),
        ("NotFoundPage", "/404", "Página não encontrada"),
    ]
    story.append(make_table(["Componente", "Rota", "Descrição"], sys_screens, cw_t))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 17. SERVIÇOS DO BACKEND
    # --------------------------------------------------------
    story.append(Paragraph("17. Serviços do Backend (17 Serviços)", styles['SectionTitle']))

    services_data = [
        ("AuthService", "auth_service.py", "Autenticação, JWT, login, refresh, bootstrap admin"),
        ("UserService", "user_service.py", "CRUD de usuários, ativação, desativação"),
        ("ProjectService", "project_service.py", "CRUD de projetos, listagem por permissão"),
        ("OrganizationService", "organization_service.py", "CRUD de organizações"),
        ("QuestionnaireService", "questionnaire_service.py", "Gerenciamento de questionários, draft, submit"),
        ("ExternalProjectService", "external_project_service.py", "Requisições externas, token, aprovação"),
        ("EmailService", "email_service.py", "Envio de emails (convite, reset, aprovação, rejeição, alerta)"),
        ("InvitationService", "invitation_service.py", "Gerenciamento de convites, tokens, aceite"),
        ("OnboardingService", "onboarding_service.py", "Wizard de 5 passos, progresso"),
        ("AgentService", "agent_service.py", "Orquestração dos 8 agentes IA (Anthropic SDK)"),
        ("OCGService", "ocg_service.py", "Geração, armazenamento e consulta de OCGs"),
        ("EvaluationService", "evaluation_service.py", "Avaliação de artefatos (7 pilares)"),
        ("CodeGenService", "codegen_service.py", "Geração de código a partir do OCG"),
        ("N8nService", "n8n_service.py", "Integração com n8n (webhooks, triggers)"),
        ("AuditService", "audit_service.py", "Registro de ações no audit_log_global"),
        ("DashboardService", "dashboard_service.py", "Métricas, estatísticas, resumos"),
        ("PasswordService", "password_service.py", "Validação de senha (10 chars, upper, digit, special)"),
    ]
    cw_sv = [avail_w * 0.20, avail_w * 0.25, avail_w * 0.55]
    story.append(make_table(["Serviço", "Arquivo", "Responsabilidade"], services_data, cw_sv))

    story.append(PageBreak())

    # --------------------------------------------------------
    # 18. GLOSSÁRIO
    # --------------------------------------------------------
    story.append(Paragraph("18. Glossário", styles['SectionTitle']))

    glossary_data = [
        ("GCA", "Gestão de Codificação Assistida — plataforma principal"),
        ("OCG", "Objeto Contexto Global — documento gerado pela análise IA com scores, stack, compliance"),
        ("GP", "Gestor de Projeto — responsável por preencher questionário e gerenciar projeto"),
        ("Pilar", "Uma das 7 dimensões de qualidade avaliadas pelo GCA (P1-P7)"),
        ("P7", "Pilar de Segurança — bloqueante se score < 70"),
        ("CodeGen", "Geração automática de código-fonte a partir do OCG aprovado"),
        ("MVP", "Minimum Viable Product — escopo mínimo funcional do projeto"),
        ("FastAPI", "Framework Python para construção de APIs REST assíncronas"),
        ("JWT", "JSON Web Token — padrão de autenticação utilizado no GCA"),
        ("LGPD", "Lei Geral de Proteção de Dados (Brasil)"),
        ("GDPR", "General Data Protection Regulation (União Europeia)"),
        ("n8n", "Plataforma open-source de automação de workflows"),
        ("Webhook", "Callback HTTP para integração entre sistemas"),
        ("BLOCKER", "Severidade máxima na verificação tecnológica — impede prosseguimento"),
        ("Draft", "Rascunho do questionário, salvo automaticamente a cada 30 segundos"),
        ("Token", "Chave temporária para convites (7d) ou projetos externos (5d)"),
        ("Wizard", "Assistente de configuração de projeto em 5 passos"),
        ("Anthropic SDK", "Biblioteca Python para integração com modelos Claude (IA)"),
        ("Claude Opus 4.6", "Modelo de IA utilizado nos 8 agentes do GCA"),
        ("asyncpg", "Driver PostgreSQL assíncrono para Python"),
        ("bcrypt", "Algoritmo de hash para armazenamento seguro de senhas"),
        ("Cloudflare Tunnel", "Serviço de proxy reverso para HTTPS e proteção DDoS"),
        ("systemd", "Sistema de inicialização do Linux usado para auto-start do GCA"),
        ("Docker Compose", "Orquestrador de containers Docker (5 serviços no GCA)"),
        ("Tailwind CSS", "Framework CSS utility-first usado no frontend"),
        ("Zustand", "Biblioteca de gerenciamento de estado para React"),
        ("TanStack Query", "Biblioteca de data fetching e cache para React"),
        ("OWASP", "Open Web Application Security Project — referência em segurança web"),
        ("SLA", "Service Level Agreement — acordo de nível de serviço"),
        ("ROI", "Return on Investment — retorno sobre investimento"),
        ("RBAC", "Role-Based Access Control — controle de acesso baseado em papéis"),
        ("HMAC", "Hash-based Message Authentication Code — autenticação de mensagens"),
    ]
    cw_g = [avail_w * 0.20, avail_w * 0.80]
    story.append(make_table(["Termo", "Definição"], glossary_data, cw_g))

    # --------------------------------------------------------
    # BUILD PDF
    # --------------------------------------------------------
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2.2 * cm,
        bottomMargin=1.8 * cm,
        title="GCA — Documento Técnico v2.0",
        author="Luiz Carlos Pielak",
    )

    doc.build(
        story,
        onFirstPage=cover_page,
        onLaterPages=header_footer,
    )
    print(f"PDF gerado com sucesso: {OUTPUT_PATH}")
    print(f"Total de elementos: {len(story)}")


if __name__ == "__main__":
    build_document()
