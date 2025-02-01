from django import template
import re
import xml.etree.ElementTree as ET
from io import StringIO

register = template.Library()

@register.filter
def split_section(text, section_header):
    """Extract content between a section header and the next section"""
    if section_header == "For P1:":
        pattern = r'<p1_advice>(.*?)</p1_advice>'
    elif section_header == "For P2:":
        pattern = r'<p2_advice>(.*?)</p2_advice>'
    else:
        # Use raw string (r prefix) for the regex pattern
        pattern = fr"{section_header}(.*?)(?=\n\w+:|$)"
        
    match = re.search(pattern, text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        # Extract items from list if present
        items = re.findall(r'<item>(.*?)</item>', content)
        if items:
            return items
        return content
    return ""

@register.filter
def is_list(value):
    """Check if value is a list"""
    return isinstance(value, (list, tuple))

@register.filter
def clean_analysis(text):
    """Remove analysis tokens from text"""
    if text:
        return text.replace('*Qant*', '')
    return text

@register.filter
def extract_advice(judgment_text, advice_type):
    """Extract advice points from the XML structure in the judgment text"""
    try:
        # Clean the text first
        judgment_text = judgment_text.replace('*Qant*', '')
        
        # Find the strengthening_advice section
        advice_match = re.search(r'<strengthening_advice>(.*?)</strengthening_advice>', judgment_text, re.DOTALL)
        if not advice_match:
            return []

        # Parse the XML
        advice_xml = f'<root>{advice_match.group(1)}</root>'
        root = ET.fromstring(advice_xml)
        
        # Extract points for the specified advice type
        points = root.findall(f'.//{advice_type}/point')
        return [point.text.strip() for point in points if point.text]
    except Exception:
        # Fallback to handle legacy format or parsing errors
        return [] 