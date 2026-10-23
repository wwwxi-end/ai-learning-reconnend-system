"""
PDF 学习计划生成器
使用 ReportLab 生成中文 PDF
"""
import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import logging

logger = logging.getLogger(__name__)


def _register_chinese_font():
    """注册中文字体（尝试多个路径）"""
    font_paths = [
        # Windows
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/SimHei.ttf',
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simsun.ttc',
        # Linux
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        # 项目内
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'fonts', 'SimHei.ttf'),
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', path))
                pdfmetrics.registerFont(TTFont('ChineseFont-Bold', path))
                return True
            except Exception as e:
                logger.warning(f"Failed to load font {path}: {e}")
                continue

    logger.warning("No Chinese font found, PDF may not display Chinese correctly")
    return False


def generate_learning_plan_pdf(student_data: dict, weak_analysis: dict,
                                recommendations: list, plan_content: str) -> bytes:
    """
    生成学习计划PDF
    返回PDF字节流
    """
    _register_chinese_font()

    buffer = io.BytesIO()

    # 页面设置
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    font_name = 'ChineseFont' if 'ChineseFont' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
    font_bold = 'ChineseFont-Bold' if 'ChineseFont-Bold' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'

    # 样式定义
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ChineseTitle',
        parent=styles['Title'],
        fontName=font_bold,
        fontSize=18,
        textColor=colors.HexColor('#1a1a2e'),
        alignment=TA_CENTER,
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'ChineseSubtitle',
        fontName=font_name,
        fontSize=11,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    h2_style = ParagraphStyle(
        'ChineseH2',
        fontName=font_bold,
        fontSize=14,
        textColor=colors.HexColor('#0f3460'),
        spaceBefore=15,
        spaceAfter=8,
        borderPad=4,
        backColor=colors.HexColor('#f0f7ff'),
        leftIndent=0
    )
    h3_style = ParagraphStyle(
        'ChineseH3',
        fontName=font_bold,
        fontSize=12,
        textColor=colors.HexColor('#333333'),
        spaceBefore=10,
        spaceAfter=5
    )
    body_style = ParagraphStyle(
        'ChineseBody',
        fontName=font_name,
        fontSize=10,
        textColor=colors.HexColor('#333333'),
        leading=16,
        spaceAfter=5,
        leftIndent=10
    )
    badge_red = ParagraphStyle('BadgeRed', fontName=font_name, fontSize=9,
                                textColor=colors.white, backColor=colors.HexColor('#ff4d4f'),
                                borderPad=3)
    badge_yellow = ParagraphStyle('BadgeYellow', fontName=font_name, fontSize=9,
                                   textColor=colors.white, backColor=colors.HexColor('#faad14'),
                                   borderPad=3)

    story = []

    # ===== 封面 =====
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("个性化学习路径推荐报告", title_style))
    story.append(Paragraph("计算机组成原理课程", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 0.5*cm))

    # 基本信息表格
    info_data = [
        ['学生姓名', student_data.get('name', '-'),
         '生成日期', datetime.now().strftime('%Y年%m月%d日')],
        ['当前均分', f"{student_data.get('avg_score', 0):.1f} 分",
         '已学知识点', f"{student_data.get('studied_count', 0)} 个"],
        ['薄弱知识点', f"{student_data.get('weak_count', 0)} 个",
         '课程进度', f"{student_data.get('progress', 0):.0f}%"],
    ]
    info_table = Table(info_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4fd')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#e8f4fd')),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTNAME', (0, 0), (0, -1), font_bold),
        ('FONTNAME', (2, 0), (2, -1), font_bold),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # ===== 薄弱点分析 =====
    story.append(Paragraph("一、薄弱点诊断报告", h2_style))

    summary = weak_analysis.get('summary', {})
    story.append(Paragraph(
        f"检测时间：{summary.get('detected_at', '-')} | "
        f"学习知识点数：{summary.get('total_kps_studied', 0)} | "
        f"个人均分：{summary.get('personal_avg', 0):.1f}分",
        body_style
    ))
    story.append(Spacer(1, 0.3*cm))

    # 薄弱点分类展示
    weak_types = [
        ('绝对薄弱（<60分）', weak_analysis.get('absolute_weak', []), '#ff4d4f'),
        ('相对薄弱（低于均分20%）', weak_analysis.get('relative_weak', []), '#fa8c16'),
        ('高危薄弱（阻塞后续知识点）', weak_analysis.get('high_risk_weak', []), '#722ed1'),
        ('遗忘趋势', weak_analysis.get('forgetting_trend', []), '#1890ff'),
    ]

    for type_name, items, color_hex in weak_types:
        if not items:
            continue
        story.append(Paragraph(f"● {type_name}（{len(items)}个）", h3_style))
        weak_table_data = [['知识点名称', '当前得分', '诊断详情']]
        for item in items[:5]:
            score_str = f"{item.get('score', 0):.0f}分" if item.get('score') is not None else '未测试'
            detail = ''
            if 'gap' in item:
                detail = f"距60分差{item['gap']:.0f}分"
            elif 'blocks_count' in item:
                detail = f"阻塞{item['blocks_count']}个后续知识点"
            elif 'slope' in item:
                detail = f"下降趋势斜率{item['slope']:.1f}"
            weak_table_data.append([item.get('kp_name', '-'), score_str, detail])

        w_table = Table(weak_table_data, colWidths=[7*cm, 3*cm, 7*cm])
        w_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(color_hex)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(w_table)
        story.append(Spacer(1, 0.2*cm))

    # ===== Top-5 推荐 =====
    story.append(Paragraph("二、个性化学习推荐（Top-5）", h2_style))
    story.append(Paragraph("根据薄弱点诊断和知识图谱前驱关系，为你生成以下学习推荐：", body_style))
    story.append(Spacer(1, 0.3*cm))

    if recommendations:
        rec_data = [['排名', '知识点', '当前分数', '推荐理由']]
        for rec in recommendations[:5]:
            score_str = f"{rec.get('current_score', 0):.0f}分" if rec.get('current_score') is not None else '未学习'
            reason = rec.get('reason', '')[:50] + ('...' if len(rec.get('reason', '')) > 50 else '')
            rec_data.append([
                f"No.{rec['rank']}",
                rec.get('kp_name', '-'),
                score_str,
                reason
            ])

        rec_table = Table(rec_data, colWidths=[1.5*cm, 5*cm, 2.5*cm, 8*cm])
        rec_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f3460')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.HexColor('#f0f7ff'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(rec_table)

    # ===== AI 学习计划内容 =====
    if plan_content:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("三、AI 个性化学习计划", h2_style))
        # 简单处理 Markdown 格式
        for line in plan_content.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.2*cm))
            elif line.startswith('## '):
                story.append(Paragraph(line[3:], h3_style))
            elif line.startswith('- ') or line.startswith('* '):
                story.append(Paragraph(f"  • {line[2:]}", body_style))
            elif len(line) > 2 and line[0].isdigit() and '. ' in line[:3]:
                story.append(Paragraph(f"  {line}", body_style))
            else:
                story.append(Paragraph(line, body_style))

    # ===== 页脚 =====
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#d0d0d0')))
    story.append(Paragraph(
        f"本报告由计算机组成原理个性化学习系统自动生成 | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle('Footer', fontName=font_name, fontSize=8,
                        textColor=colors.HexColor('#999999'), alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()
