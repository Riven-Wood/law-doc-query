#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
law_query.py - 法律文档库只读查询工具
提供给 Agent 调用，用于在 Markdown 法律文档库中精准定位法条、查询裁判文书、验证引用。

支持的文件类型（自动识别）：
- normative   规范性文件（法律法规、司法解释等，含"第X条"结构）
- case        裁判文书（判决书/裁定书等，含案号、"本院认为"等结构）
- commentary  理解与适用 / 条文释义（解释性文本）
- other       其他

特性：
- 纯标准库实现，无外部依赖
- 所有子命令输出 JSON，每个结果带 source 字段（文件名:行号）便于溯源
- 仅只读，无网络，无写操作，无命令执行
- 支持"第X条"中文数字与阿拉伯数字互转
- 文件名模糊匹配（输入"民法典"可命中"中华人民共和国民法典.md"）
- 本工具仅查询本地文档库（LAW_DOCS_DIR）；外部知识库（如 ima）由 Agent 通过 MCP 调用，本脚本不直接访问
"""
import os
import re
import sys
import json
import argparse
from pathlib import Path

CN_NUM = {
    '零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000,
}


def cn2num(s):
    """中文数字转 int，如 '一百二十三' -> 123。已是数字则直接返回。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if not s:
        return None
    total = 0
    current = 0
    for ch in s:
        if ch not in CN_NUM:
            return None
        v = CN_NUM[ch]
        if v >= 10:
            if current == 0:
                current = 1
            total += current * v
            current = 0
        else:
            current = v
    total += current
    return total if total > 0 else None


ARTICLE_RE = re.compile(r'第([一二三四五六七八九十百千零〇\d两]+)条')
CASE_NO_RE = re.compile(r'（(?:20\d{2}|19\d{2})）[^）\n]{1,30}号')
SECTION_MARKERS = [
    '原告诉称', '被告辩称', '答辩称', '反诉称',
    '经审理查明', '本院认为', '本院审查',
    '判决如下', '裁定如下', '调解协议',
]


def find_article_no(text):
    """若 text 含'第X条'，返回条号(int)；否则 None。宽松匹配，用于类型识别。"""
    m = ARTICLE_RE.search(text)
    if m:
        return cn2num(m.group(1))
    return None


# 条文起始行：行首（允许前导空白/# 标记）紧跟"第X条"，且其后不紧跟"规定/款/项/目/之/法"
# 等引用后缀。用于精确划定条文边界，避免正文内交叉引用（如"依据本法第144条规定"）
# 被误判为新条文而导致本条正文被截断。
ARTICLE_START_RE = re.compile(
    r'^\s*#*\s*第([一二三四五六七八九十百千零〇\d两]+)条(?![规定款项目之法])'
)


def find_article_start(text):
    """判断 text 是否为条文起始行。返回条号(int)或 None。

    与 find_article_no 的区别：仅认行首"第X条"且排除引用后缀，
    因此正文内的"依据本法第X条规定"等交叉引用不会被识别为新条文。
    """
    m = ARTICLE_START_RE.search(text)
    if m:
        return cn2num(m.group(1))
    return None


def detect_type(lines, name):
    """识别文件类型：normative / case / commentary / other。"""
    if lines and lines[0].strip() == '---':
        for line in lines[1:50]:
            if line.strip() == '---':
                break
            m = re.match(r'type:\s*(\S+)', line)
            if m:
                return m.group(1).strip().lower()
    head = '\n'.join(lines[:80])
    full = '\n'.join(lines)
    name_lower = name.lower()
    if any(k in name for k in ['判决书', '裁定书', '调解书', '支付令', '决定书']) or \
       CASE_NO_RE.search(head):
        return 'case'
    if any(k in name for k in ['法', '条例', '办法', '规定', '解释', '细则', '规则', '通则']) or \
       find_article_start(head) is not None:
        return 'normative'
    if any(k in name for k in ['理解与适用', '释义', '解读', '条文释义']):
        return 'commentary'
    return 'other'


def extract_sections(lines):
    """提取裁判文书的结构化段落。返回 [{name, line_start, line_end, text}]。"""
    sections = []
    current = None
    for i, line in enumerate(lines):
        hit = None
        for marker in SECTION_MARKERS:
            if marker in line[:30]:
                hit = marker
                break
        if hit:
            if current:
                current['line_end'] = i
                current['text'] = '\n'.join(lines[current['line_start']:i])
                sections.append(current)
            current = {'name': hit, 'line_start': i, 'line_end': len(lines)}
    if current:
        current['text'] = '\n'.join(lines[current['line_start']:current['line_end']])
        sections.append(current)
    return sections


def get_docs_dir():
    d = os.environ.get('LAW_DOCS_DIR')
    if d:
        return Path(d)
    return Path.cwd()


def resolve_file(name):
    """模糊匹配文件名。返回 Path 或 None。做了路径遍历防护。"""
    docs = get_docs_dir().resolve()
    name = name.strip()
    name = name.replace('\\', '/').split('/')[-1]
    if '..' in name:
        return None
    stem = name[:-3] if name.endswith('.md') else name
    if not stem:
        return None
    p = (docs / (stem + '.md')).resolve()
    try:
        p.relative_to(docs)
    except ValueError:
        return None
    if p.exists():
        return p
    candidates = [f for f in docs.glob('*.md') if stem in f.stem]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda x: len(x.stem))


def read_lines(path):
    return path.read_text(encoding='utf-8').splitlines()


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_list(args):
    docs = get_docs_dir()
    files = sorted(docs.glob('*.md'))
    result = []
    for f in files:
        try:
            lines = read_lines(f)
        except Exception as e:
            result.append({'file': f.name, 'error': str(e)})
            continue
        ftype = detect_type(lines, f.name)
        articles = []
        for i, line in enumerate(lines, 1):
            no = find_article_start(line)
            if no is not None:
                articles.append({'no': no, 'line': i})
        entry = {
            'file': f.name,
            'type': ftype,
            'lines': len(lines),
            'article_count': len(articles),
            'source': f.name,
        }
        if ftype == 'case':
            text = '\n'.join(lines)
            m = CASE_NO_RE.search(text)
            if m:
                entry['case_no'] = m.group(0)
        if articles:
            entry['articles'] = articles
        result.append(entry)
    emit({'docs': result, 'count': len(result)})


def cmd_outline(args):
    f = resolve_file(args.file)
    if not f:
        emit({'error': f'文件未找到: {args.file}'})
        sys.exit(1)
    lines = read_lines(f)
    ftype = detect_type(lines, f.name)
    outline = []
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            title = stripped.lstrip('#').strip()
            entry = {'line': i, 'level': level, 'type': 'heading', 'text': title}
            no = find_article_start(title)
            if no is not None:
                entry['article_no'] = no
            outline.append(entry)
        else:
            no = find_article_start(stripped)
            if no is not None:
                outline.append({
                    'line': i, 'level': 0, 'type': 'article',
                    'text': stripped[:80], 'article_no': no,
                })
    emit({'file': f.name, 'type': ftype, 'outline': outline, 'source': f.name})


def cmd_search(args):
    docs = get_docs_dir()
    keyword = args.keyword
    ctx = args.context
    type_filter = args.type
    matches = []
    for f in sorted(docs.glob('*.md')):
        try:
            lines = read_lines(f)
        except Exception:
            continue
        if type_filter:
            ftype = detect_type(lines, f.name)
            if ftype != type_filter:
                continue
        for i, line in enumerate(lines):
            if keyword in line:
                start = max(0, i - ctx)
                end = min(len(lines), i + ctx + 1)
                matches.append({
                    'file': f.name,
                    'type': detect_type(lines, f.name) if not type_filter else type_filter,
                    'line': i + 1,
                    'matched': line.strip(),
                    'context': [
                        {'line': start + j + 1, 'text': lines[start + j]}
                        for j in range(end - start)
                    ],
                    'source': f'{f.name}:{i + 1}',
                })
    emit({'keyword': keyword, 'type_filter': type_filter, 'matches': matches, 'count': len(matches)})


def cmd_article(args):
    f = resolve_file(args.law_name)
    if not f:
        emit({'error': f'法律文档未找到: {args.law_name}'})
        sys.exit(1)
    target = cn2num(args.article_no) if not args.article_no.isdigit() else int(args.article_no)
    if target is None:
        emit({'error': f'无法解析条号: {args.article_no}'})
        sys.exit(1)
    lines = read_lines(f)
    all_articles = []
    for i, line in enumerate(lines):
        no = find_article_start(line)
        if no is not None:
            all_articles.append((no, i))
    start_idx = None
    next_idx = len(lines)
    for idx, (no, line_i) in enumerate(all_articles):
        if no == target:
            start_idx = line_i
            if idx + 1 < len(all_articles):
                next_idx = all_articles[idx + 1][1]
            break
    if start_idx is None:
        emit({
            'error': f'未找到第{target}条',
            'file': f.name,
            'available': sorted({a[0] for a in all_articles}),
        })
        sys.exit(1)
    body = lines[start_idx:next_idx]
    emit({
        'file': f.name,
        'type': detect_type(lines, f.name),
        'article_no': target,
        'line_start': start_idx + 1,
        'line_end': next_idx,
        'text': '\n'.join(body),
        'source': f'{f.name}:{start_idx + 1}-{next_idx}',
    })


def cmd_case(args):
    """查询裁判文书：可按文件名查单篇，或按案号跨文件检索。"""
    if args.case_no:
        docs = get_docs_dir()
        found = []
        for f in sorted(docs.glob('*.md')):
            try:
                lines = read_lines(f)
            except Exception:
                continue
            text = '\n'.join(lines)
            if args.case_no in text:
                found.append(_build_case_result(f, lines, text))
        emit({'query': args.case_no, 'matches': found, 'count': len(found)})
        return
    if not args.file:
        emit({'error': '请提供文件名或 --case-no 案号'})
        sys.exit(1)
    f = resolve_file(args.file)
    if not f:
        emit({'error': f'文件未找到: {args.file}'})
        sys.exit(1)
    lines = read_lines(f)
    text = '\n'.join(lines)
    emit(_build_case_result(f, lines, text))


def _build_case_result(f, lines, text):
    """构造裁判文书的结构化结果。"""
    m = CASE_NO_RE.search(text)
    case_no = m.group(0) if m else None
    sections = extract_sections(lines)
    sec_out = []
    for s in sections:
        sec_out.append({
            'name': s['name'],
            'line_start': s['line_start'] + 1,
            'line_end': s['line_end'],
            'source': f'{f.name}:{s["line_start"] + 1}-{s["line_end"]}',
        })
    result = {
        'file': f.name,
        'type': 'case',
        'case_no': case_no,
        'sections': sec_out,
        'source': f.name,
    }
    # 提取关键段落原文
    for s in sections:
        if s['name'] in ('本院认为', '本院审查'):
            result['reasoning'] = s['text']
            result['reasoning_source'] = f'{f.name}:{s["line_start"] + 1}-{s["line_end"]}'
        elif s['name'] in ('判决如下', '裁定如下'):
            result['ruling'] = s['text']
            result['ruling_source'] = f'{f.name}:{s["line_start"] + 1}-{s["line_end"]}'
    return result


def cmd_read(args):
    f = resolve_file(args.file)
    if not f:
        emit({'error': f'文件未找到: {args.file}'})
        sys.exit(1)
    lines = read_lines(f)
    if args.section:
        start_idx = None
        next_idx = len(lines)
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith('#') and args.section in stripped:
                start_idx = i
                level = len(stripped) - len(stripped.lstrip('#'))
                for j in range(i + 1, len(lines)):
                    s2 = lines[j].lstrip()
                    if s2.startswith('#'):
                        lv2 = len(s2) - len(s2.lstrip('#'))
                        if lv2 <= level:
                            next_idx = j
                            break
                break
        if start_idx is None:
            emit({'error': f'章节未找到: {args.section}'})
            sys.exit(1)
        body = lines[start_idx:next_idx]
        emit({
            'file': f.name,
            'type': detect_type(lines, f.name),
            'section': args.section,
            'line_start': start_idx + 1,
            'line_end': next_idx,
            'text': '\n'.join(body),
            'source': f'{f.name}:{start_idx + 1}-{next_idx}',
        })
    else:
        start = (args.from_ or 1) - 1
        end = args.to or len(lines)
        start = max(0, start)
        end = min(len(lines), end)
        body = lines[start:end]
        emit({
            'file': f.name,
            'type': detect_type(lines, f.name),
            'line_start': start + 1,
            'line_end': end,
            'text': '\n'.join(body),
            'source': f'{f.name}:{start + 1}-{end}',
        })


def cmd_verify(args):
    f = resolve_file(args.file)
    if not f:
        emit({'error': f'文件未找到: {args.file}'})
        sys.exit(1)
    lines = read_lines(f)
    start = args.from_ - 1
    end = args.to
    start = max(0, start)
    end = min(len(lines), end)
    actual = '\n'.join(lines[start:end])
    expect = args.expect
    match_count = actual.count(expect)
    unique = match_count == 1
    passed = match_count >= 1
    emit({
        'file': f.name,
        'type': detect_type(lines, f.name),
        'line_start': start + 1,
        'line_end': end,
        'expected': expect,
        'actual_excerpt': actual[:500],
        'verified': passed,
        'match_count': match_count,
        'unique': unique,
        'source': f'{f.name}:{start + 1}-{end}',
    })


def main():
    p = argparse.ArgumentParser(description='法律文档库只读查询工具')
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('list', help='列出所有法律文档（含类型识别）')

    p_outline = sub.add_parser('outline', help='输出文件大纲')
    p_outline.add_argument('file')

    p_search = sub.add_parser('search', help='跨文件关键词搜索')
    p_search.add_argument('keyword')
    p_search.add_argument('--context', type=int, default=2)
    p_search.add_argument('--type', choices=['normative', 'case', 'commentary', 'other'],
                          help='只搜某类文件')

    p_article = sub.add_parser('article', help='精确取某法某条（规范性文件）')
    p_article.add_argument('law_name')
    p_article.add_argument('article_no')

    p_case = sub.add_parser('case', help='查询裁判文书')
    p_case.add_argument('file', nargs='?', help='文件名（查单篇）')
    p_case.add_argument('--case-no', dest='case_no', help='按案号跨文件检索')

    p_read = sub.add_parser('read', help='读取文件行段或章节')
    p_read.add_argument('file')
    p_read.add_argument('--from', dest='from_', type=int)
    p_read.add_argument('--to', type=int)
    p_read.add_argument('--section')

    p_verify = sub.add_parser('verify', help='核对行段是否含某原文')
    p_verify.add_argument('file')
    p_verify.add_argument('--from', dest='from_', type=int, required=True)
    p_verify.add_argument('--to', type=int, required=True)
    p_verify.add_argument('--expect', required=True)

    args = p.parse_args()
    {
        'list': cmd_list,
        'outline': cmd_outline,
        'search': cmd_search,
        'article': cmd_article,
        'case': cmd_case,
        'read': cmd_read,
        'verify': cmd_verify,
    }[args.cmd](args)


if __name__ == '__main__':
    main()
