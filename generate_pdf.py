#!/usr/bin/env python3
"""
MSAJCE Admission Page — RAG Extract PDF Generator
Uses reportlab only. All table cells wrapped in Paragraph objects.
"""

import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN      = HexColor("#2d6a4f")
DARKGREEN  = HexColor("#1b4332")
LIGHTGREEN = HexColor("#40916c")
NAVY       = HexColor("#1a1a2e")
ROWGREY    = HexColor("#f5f5f5")
BORDER     = HexColor("#bbbbbb")
AMBER      = HexColor("#7a4f00")
GREY       = HexColor("#555555")
CHUNKGREY  = HexColor("#888888")

# ── Styles ───────────────────────────────────────────────────────────────────
def get_styles():
    s = {}
    s['h1'] = ParagraphStyle(
        'h1', fontSize=22, leading=26, textColor=DARKGREEN,
        alignment=TA_CENTER, spaceAfter=10, fontName='Helvetica-Bold'
    )
    s['h2'] = ParagraphStyle(
        'h2', fontSize=14, leading=18, textColor=NAVY,
        spaceBefore=15, spaceAfter=8, fontName='Helvetica-Bold',
        leftIndent=0
    )
    s['body'] = ParagraphStyle(
        'body', fontSize=10, leading=13, textColor=GREY,
        spaceAfter=6, fontName='Helvetica'
    )
    s['meta'] = ParagraphStyle(
        'meta', fontSize=8, leading=10, textColor=CHUNKGREY,
        fontName='Helvetica-Oblique', spaceAfter=2
    )
    s['table_cell'] = ParagraphStyle(
        'table_cell', fontSize=9, leading=11, textColor=NAVY,
        fontName='Helvetica'
    )
    s['table_header'] = ParagraphStyle(
        'table_header', fontSize=9, leading=11, textColor=white,
        fontName='Helvetica-Bold', alignment=TA_CENTER
    )
    s['contact_title'] = ParagraphStyle(
        'contact_title', fontSize=10, leading=12, textColor=white,
        fontName='Helvetica-Bold'
    )
    s['contact_info'] = ParagraphStyle(
        'contact_info', fontSize=9, leading=11, textColor=white,
        fontName='Helvetica'
    )
    return s

# ── Table Builder ────────────────────────────────────────────────────────────
def create_styled_table(data_rows, col_widths, styles):
    """
    Expects data_rows where each cell is either a string or a list of flowables.
    We convert strings to Paragraphs.
    """
    formatted_data = []
    for row in data_rows:
        new_row = []
        for i, cell in enumerate(row):
            if isinstance(cell, str):
                # Apply header style if it's the first row
                style = styles['table_header'] if formatted_data == [] else styles['table_cell']
                new_row.append(Paragraph(cell, style))
            else:
                new_row.append(cell)
        formatted_data.append(new_row)

    tbl = Table(formatted_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), GREEN),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, ROWGREY]),
    ]))
    return tbl

# ── Entity Card Builder ──────────────────────────────────────────────────────
def create_entity_banner(entity, styles):
    name = entity.get('name', 'Unknown')
    role = entity.get('role', 'Personnel')
    dept = entity.get('department', 'N/A')
    
    # Simple block for entity
    data = [[
        Paragraph(f"<b>{name}</b>", styles['contact_title']),
        Paragraph(f"{role} | {dept}", styles['contact_info'])
    ]]
    t = Table(data, colWidths=[6*cm, 12*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    return t

# ── Main Generator ───────────────────────────────────────────────────────────
def build_pdf(json_path, output_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm
    )
    
    styles = get_styles()
    story = []

    # 1. Header
    story.append(Paragraph("MSAJCE Admission Intelligence Report", styles['h1']))
    story.append(Paragraph("Proprietary RAG Knowledge Extraction", styles['meta']))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=0.5*cm))

    # 2. Metadata Summary
    meta = data.get('metadata', {})
    story.append(Paragraph("Extraction Metadata", styles['h2']))
    meta_text = (
        f"<b>Source URL:</b> {meta.get('source_url', 'N/A')}<br/>"
        f"<b>Model:</b> {meta.get('embedding_model', 'N/A')}<br/>"
        f"<b>Total Chunks:</b> {len(data.get('chunks', []))}<br/>"
        f"<b>Scraped Date:</b> {meta.get('scraped_date', 'N/A')}"
    )
    story.append(Paragraph(meta_text, styles['body']))
    story.append(Spacer(1, 0.5*cm))

    # 3. Process Chunks
    for i, chunk in enumerate(data.get('chunks', [])):
        elements = []
        section_name = chunk.get('section', f"Section {i+1}")
        
        # Section Title
        elements.append(Paragraph(f"{section_name}", styles['h2']))
        
        # Chunk Meta
        c_meta = f"ID: {chunk.get('chunk_id')} | Tokens: {chunk.get('token_count')}"
        elements.append(Paragraph(c_meta, styles['meta']))
        
        # Main Text
        text = chunk.get('text', '').replace('\n', '<br/>')
        elements.append(Paragraph(text, styles['body']))

        # Entities (if any)
        entities = chunk.get('entities', [])
        if entities:
            elements.append(Spacer(1, 0.2*cm))
            for ent in entities:
                elements.append(create_entity_banner(ent, styles))
                elements.append(Spacer(1, 0.1*cm))

        # Possible Questions
        qs = chunk.get('possible_questions', [])
        if qs:
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph("<b>Potential Queries:</b>", styles['table_cell']))
            for q in qs:
                elements.append(Paragraph(f"• {q}", styles['body']))

        elements.append(Spacer(1, 0.5*cm))
        elements.append(HRFlowable(width="80%", thickness=0.5, color=BORDER, dash=(2,2)))
        elements.append(Spacer(1, 0.5*cm))

        # Keep chunk together to avoid awkward splits
        story.append(KeepTogether(elements))

    # Final Save
    doc.build(story)
    print(f"PDF generated: {output_path}")

if __name__ == "__main__":
    # Adjust paths as needed for your environment
    import os
    json_file = "msajce_admission.json"
    pdf_file = "msajce_admission.pdf"
    
    if os.path.exists(json_file):
        build_pdf(json_file, pdf_file)
    else:
        print(f"Error: {json_file} not found.")
