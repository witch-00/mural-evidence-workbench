"""Single-page, evidence-aware observation report. Does not certify statements."""
from collections import Counter
from datetime import datetime, timezone, timedelta
from html import escape
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as PDFImage, Paragraph, Spacer, Table, TableStyle

INK = colors.HexColor('#24342e')
GREEN = colors.HexColor('#244c40')
RUST = colors.HexColor('#974e36')
RULE = colors.HexColor('#d7d8cf')
PAPER = colors.HexColor('#f4f4ed')
WIDTH = A4[0] - 64
SOURCE_TYPES = {'image': '原图对照', 'reference': '资料对照', 'opinion': '无直接依据'}
DECISIONS = {'adopt': '采纳描述', 'revise': '修改后采纳', 'reject': '不采纳', 'insufficient': '本图无法判断'}
LEGACY_DECISIONS = {'保留观察': 'adopt', '修正观察': 'revise', '暂缓判断': 'insufficient'}
REASONS = {
    'visible': '原图可见特征与描述相符', 'reference_match': '参考资料与该处特征相符',
    'overstated': '原描述超出了图像所能支持的范围', 'motif': '该处更符合原有笔线或纹样',
    'artifact': '拍摄、光照或画质影响了辨识', 'no_feature': '原图未见描述所指的异常特征',
    'extent': '原描述的位置或范围不准确', 'resolution': '图像分辨率不足以辨识该处细节',
    'cause': '仅凭照片无法判定该现象的成因', 'no_reference': '缺少可供对照的资料',
    'other': '其他理由',
}
REASON_CHOICES = {
    'adopt': ('visible', 'reference_match', 'other'),
    'revise': ('overstated', 'motif', 'artifact', 'extent', 'other'),
    'reject': ('no_feature', 'motif', 'artifact', 'overstated', 'other'),
    'insufficient': ('resolution', 'artifact', 'cause', 'no_reference', 'other'),
}


def register_fonts(root):
    for weight in ('Regular', 'Semibold'):
        name = 'MuralSerifSC-' + weight
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(Path(root) / 'static/fonts' / (name + '.ttf'))))
    pdfmetrics.registerFontFamily('MuralSerifSC-Regular', normal='MuralSerifSC-Regular',
                                  bold='MuralSerifSC-Semibold', italic='MuralSerifSC-Regular',
                                  boldItalic='MuralSerifSC-Semibold')


def validate_evidence(doc, raw, version, checked_text, error):
    """Validate provenance structure; never infer that a claim is true from text."""
    if type(version) is not int or version not in (1, 2):
        raise error('无法识别该区域证据卡的格式。')
    for region, row in zip(doc['regions'], raw):
        rid, value = region['id'], row.get('evidence')
        if not isinstance(value, dict):
            raise error(f'请打开 {rid}，选择本次结论。')
        raw_decision = value.get('decision')
        if not isinstance(raw_decision, str):
            raise error(f'{rid} 的本次结论格式无效。')
        decision = LEGACY_DECISIONS.get(raw_decision, raw_decision)
        if decision not in DECISIONS:
            raise error(f'请打开 {rid}，选择本次结论：采纳描述、修改后采纳、不采纳或本图无法判断。')
        kind = value.get('source_type', '')
        if not isinstance(kind, str) or (kind and kind not in SOURCE_TYPES):
            raise error(f'{rid} 的依据类型无效，请重新选择。')
        if version == 2 and not kind:
            raise error(f'请打开 {rid}，选择依据类型：原图对照、资料对照或个人意见。')
        if kind == 'opinion' and decision in ('adopt', 'revise'):
            raise error(f'{rid} 没有直接依据，不能采纳该描述。请补充原图或资料依据，或选择“不采纳／本图无法判断”。')
        if kind == 'reference' and doc['references'] == '未提供':
            raise error(f'{rid} 引用了资料，请在“图像与资料”的参考资料来源中登记标题、页码或链接。')
        code = value.get('reason_code', '')
        if not isinstance(code, str) or (code and code not in REASON_CHOICES[decision]):
            raise error(f'{rid} 的理由与本次结论不符，请重新选择理由。')
        if version == 2 and not code:
            raise error(f'请打开 {rid}，选择本次结论的理由。')
        if code == 'reference_match' and kind != 'reference':
            raise error(f'{rid} 选择了资料相符，请将依据类型设为“资料对照”并登记出处。')
        if decision == 'revise' and row.get('ai_observation') == region['observation']:
            raise error(f'{rid} 的描述尚未修改，请先修订描述，或选择“采纳描述”。')
        include_note = value.get('include_note', False)
        if type(include_note) is not bool:
            raise error(f'{rid} 的补充说明选项格式无效。')
        evidence = {'decision': decision, 'source_type': kind, 'reason_code': code, 'include_note': include_note}
        fields = [('reference', '依据位置与特征', 80, version == 1 or decision in ('adopt', 'revise')),
                  ('alternative', '其他可能解释', 60, False),
                  ('reason', '补充意见', 80, version == 1 or code == 'other'),
                  ('follow_up', '判断边界', 60, False)]
        for key, label, limit, required in fields:
            if not isinstance(value.get(key, ''), str):
                raise error(f'{rid} 的{label}格式无效。')
            evidence[key] = checked_text(value.get(key), limit, f'{rid} 的{label}', required)
        region['evidence'] = evidence
        region['ai_observation'] = checked_text(row.get('ai_observation'), 100, f'{rid} 的 AI 初稿')


def _paragraph(text, size=9.5, leading=None, bold=False, color=INK):
    style = ParagraphStyle('card', fontName='MuralSerifSC-Semibold' if bold else 'MuralSerifSC-Regular',
                           fontSize=size, leading=leading or size * 1.4, textColor=color,
                           alignment=TA_LEFT, wordWrap='CJK', splitLongWords=True,
                           spaceAfter=0, spaceBefore=0, allowWidows=0, allowOrphans=0)
    return Paragraph(text, style)


def _text(value):
    return escape(str(value or '')).replace('\n', '<br/>')


def _entries(items, size):
    return _paragraph('<br/>'.join('<b>' + _text(label) + '</b>　' + _text(value)
                                 for label, value in items if value), size)


def _table(headings, rows, widths, size, compact=False):
    data = [[_paragraph(_text(label), size, bold=True, color=GREEN) for label in headings]] + rows
    table = Table(data, colWidths=widths, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 3 if compact else 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if compact else 7),
        ('BACKGROUND', (0, 0), (-1, 0), PAPER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafaf7')]),
        ('GRID', (0, 0), (-1, -1), .45, RULE),
        ('LINEBELOW', (0, 0), (-1, 0), .8, GREEN),
    ]))
    return table


def _heading(number, text):
    return _paragraph(f'<font color="#974e36">{number}</font>　{_text(text)}', 11, 15, bold=True)


def _marked_original(image, regions):
    result = image.copy()
    draw = ImageDraw.Draw(result)
    stroke = max(2, round(max(image.size) / 420))
    # Vector numbers are added separately on the PDF so they remain legible at any image scale.
    for region in regions:
        x, y = region['x'] * image.width, region['y'] * image.height
        draw.rectangle((x, y, x + region['w'] * image.width, y + region['h'] * image.height),
                       outline='#d69a32', width=stroke)
    return result


def _locator(image, region, ratio):
    """Expand a crop with real neighboring pixels, retaining the whole region."""
    w, h = region['w'] * image.width, region['h'] * image.height
    vw = max(w * 1.12, h * 1.12 * ratio)
    vh = vw / ratio
    if vw > image.width or vh > image.height:
        scale = min(image.width / vw, image.height / vh)
        vw, vh = vw * scale, vh * scale
    if vw < w or vh < h:
        # When the whole region cannot fit the desired aspect, show it without clipping.
        vw, vh = w, h
    cx = (region['x'] + region['w'] / 2) * image.width
    cy = (region['y'] + region['h'] / 2) * image.height
    left = max(0, min(image.width - vw, cx - vw / 2))
    top = max(0, min(image.height - vh, cy - vh / 2))
    return _marked_original(image, [region]).crop((round(left), round(top), round(left + vw), round(top + vh)))


class _RegionImage(PDFImage):
    def draw(self):
        super().draw()
        for r in self.regions:
            x, y = r['x'] * self.drawWidth, (1 - r['y']) * self.drawHeight
            y = min(self.drawHeight - 10, y)
            self.canv.setFillColor(RUST)
            badge = pdfmetrics.stringWidth(r['id'], 'MuralSerifSC-Semibold', 7) + 6
            self.canv.rect(x, y, badge, 10, fill=1, stroke=0)
            self.canv.setFillColor(colors.white)
            self.canv.setFont('MuralSerifSC-Semibold', 7)
            self.canv.drawString(x + 3, y + 2, r['id'])


def _image_flow(image, width, height, regions=()):
    factor = min(width / image.width, height / image.height)
    raster = image.copy()
    raster.thumbnail((round(width * 3), round(height * 3)), Image.Resampling.LANCZOS)
    stream = BytesIO()
    raster.save(stream, 'PNG')
    stream.seek(0)
    flow = _RegionImage(stream, image.width * factor, image.height * factor)
    flow.regions = regions
    flow.hAlign = 'CENTER'
    return flow


def _image_table(doc, height):
    n = len(doc['regions'])
    widths = [232] + [(WIDTH - 232) / n] * n
    panels = [_marked_original(doc['image'], doc['regions'])]
    panels += [_locator(doc['image'], r, (widths[1] - 12) / height) for r in doc['regions']]
    captions = ['原图 · 关注区域定位'] + [r['id'] + ' 原图局部 · 含周边' for r in doc['regions']]
    table = Table([[_paragraph(_text(v), 8.5, bold=True, color=GREEN) for v in captions],
                   [_image_flow(im, w - 12, height, doc['regions'] if i == 0 else ())
                    for i, (im, w) in enumerate(zip(panels, widths))]], colWidths=widths,
                  rowHeights=[19, height + 4])
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 6),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                               ('TOPPADDING', (0, 0), (-1, -1), 0),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    return table


def _flows(doc, size, image_height, compact=False):
    def gap(height):
        return Spacer(1, (4 if height <= 6 else 6) if compact else height)
    flows = [_heading('01', '原图与关注区域'), gap(6), _image_table(doc, image_height), gap(12),
             _heading('02', '区域观察与核对记录'), gap(6)]
    rows = []
    for region in doc['regions']:
        evidence = region.get('evidence', {})
        initial = region.get('ai_observation', '')
        observation = region['observation']
        origin = region['origin']
        decision = evidence.get('decision')
        if decision in ('reject', 'insufficient'):
            claims = [('AI 原文（未采纳）' if initial or origin == 'AI 初稿' else '原描述（未采纳）', initial or observation),
                      ('本次结论', '不采纳该项描述' if decision == 'reject' else '仅凭本图无法作出该项判断')]
        elif initial and initial != observation:
            claims = [('AI 初稿', initial), ('人工修订', observation)]
        else:
            label = {'AI 初稿': 'AI 观察', '人工填写': '人工观察',
                     '人工修订 AI': '人工修订', '旧版来源待核': '历史观察'}.get(origin, origin)
            claims = [(label, observation)]
        if evidence.get('include_note'):
            claims += [('其他解释', evidence.get('alternative'))]
        support = [('依据类型', SOURCE_TYPES.get(evidence.get('source_type'), '旧记录未分类')),
                   ('依据记录', evidence.get('reference')),
                   ('选择理由', REASONS.get(evidence.get('reason_code'))),
                   ('自定义理由' if evidence.get('reason_code') == 'other' else '补充意见',
                    evidence.get('reason') if evidence.get('include_note') or evidence.get('reason_code') == 'other' else ''),
                   ('本次取舍', DECISIONS.get(decision, '旧记录未选择')),
                   ('判断边界', evidence.get('follow_up') if evidence.get('include_note') else '')]
        rows.append([_paragraph(_text(region['id']), size + 1, bold=True, color=RUST),
                     _entries(claims, size), _entries(support, size)])
    if all('evidence' not in region for region in doc['regions']):
        observations = _table(['区域', '观察记录与来源'], [row[:2] for row in rows], [39, WIDTH - 39], size, compact)
    else:
        observations = _table(['区域', '观察与分歧', '依据与复核'], rows, [39, 231, WIDTH - 270], size, compact)
    flows += [observations, gap(12),
              _heading('03', '建议行动与风险边界'), gap(6)]
    rows = [[_paragraph(_text(row['target']), size, bold=True, color=RUST),
             _entries([(row['origin'], row['action'])], size),
             _paragraph(_text(row['basis']), size), _paragraph(_text(row['risk']), size)] for row in doc['advice']]
    flows += [_table(['目标', '建议行动', '图像依据', '风险与限制'], rows, [48, 171, 154, WIDTH - 373], size, compact),
              gap(10), _entries([('判断边界', doc['uncertainty'])], size), gap(12),
              _heading('04', '素材来源与 AI 参与'), gap(6)]
    counts = Counter(row['origin'] for row in doc['regions'])
    roles = '；'.join(f'{key} {value} 处' for key, value in counts.items())
    metadata = [('图片与授权', doc['source']), ('参考资料', doc['references']),
                ('AI 参与', doc['model'] + '。区域记录：' + roles + '。'),
                ('工具与记录', '壁画智护工作台 · Pillow · ReportLab' +
                 ('；' + doc['other_tools'] if doc['other_tools'] else ''))]
    rows = [[_paragraph(_text(key), 8, bold=True, color=GREEN), _paragraph(_text(value), 8, 11)] for key, value in metadata]
    table = Table(rows, colWidths=[66, WIDTH - 66])
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 5),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                               ('TOPPADDING', (0, 0), (-1, -1), 1 if compact else 3),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 1 if compact else 3),
                               ('LINEBELOW', (0, 0), (-1, -1), .35, RULE)]))
    flows.append(table)
    return flows


def render_observation(doc, fingerprint, root, error):
    register_fonts(root)
    top, bottom = 752, 62
    # Try normal typography first; shorten content rather than exporting tiny print or clipping.
    for size, image_height, compact in ((9.5, 126, False), (9.5, 105, False), (9.0, 105, False), (9.0, 90, True)):
        flows = _flows(doc, size, image_height, compact)
        heights = [flow.wrap(WIDTH, A4[1])[1] for flow in flows]
        if sum(heights) <= top - bottom:
            break
    else:
        raise error('区域观察、复核依据或资料来源过长，无法以清晰字号排入一页。请精简重复内容后导出；完整过程仍可保存在工作文件。')
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle('壁画智护 · AI 壁画观察卡')
    c.setAuthor('壁画智护工作台')
    c.setSubject('图像观察、人工取舍与依据记录')
    c.setCreator('壁画智护工作台')
    c.setFillColor(RUST)
    c.rect(32, 791, 3, 25, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont('MuralSerifSC-Semibold', 23)
    c.drawString(44, 796, 'AI 壁画观察卡')
    c.setFont('MuralSerifSC-Regular', 9)
    c.drawRightString(A4[0] - 32, 805, '壁画智护  /  图像初步观察')
    c.setFont('MuralSerifSC-Regular', 8)
    c.setFillColor(GREEN)
    c.drawString(44, 779, '观察 · 对照 · 记录')
    date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y.%m.%d  %H:%M  UTC+8')
    c.drawRightString(A4[0] - 32, 779, date)
    c.setStrokeColor(GREEN)
    c.setLineWidth(.8)
    c.line(32, 767, A4[0] - 32, 767)
    y = top
    for flow, height in zip(flows, heights):
        flow.drawOn(c, 32, y - height)
        y -= height
    c.setStrokeColor(RULE)
    c.line(32, 49, A4[0] - 32, 49)
    c.setFont('MuralSerifSC-Regular', 7.5)
    c.setFillColor(GREEN)
    c.drawString(32, 36, '人工复核范围：原图可见信息与所列资料；本卡不对材质、成因或实体修复作鉴定。')
    c.setFont('MuralSerifSC-Regular', 7)
    if fingerprint:
        c.drawString(32, 23, '记录指纹  ' + fingerprint.upper())
    c.drawRightString(A4[0] - 32, 23, '壁画智护  ·  1 / 1')
    c.showPage()
    c.save()
    return out.getvalue()
