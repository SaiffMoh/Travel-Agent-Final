from Models.ExtractedInfo import ExtractedInfo

def question_to_html(question: str, extracted_info: ExtractedInfo) -> str:
    """Format follow-up question with current info as HTML"""
    html = f"<div class='question-response'>"
    html += f"<div class='question'>"
    html += f"<p>{question}</p>"
    html += f"</div>"
    
    # Show current progress
    info_items = []
    if extracted_info.departure_date:
        info_items.append(f"📅 {extracted_info.departure_date}")
    if extracted_info.origin:
        info_items.append(f"🛫 From {extracted_info.origin}")
    if extracted_info.destination:
        info_items.append(f"🛬 To {extracted_info.destination}")
    if extracted_info.cabin_class:
        info_items.append(f"💺 {extracted_info.cabin_class.title()}")
    if extracted_info.duration:
        info_items.append(f"📆 {extracted_info.duration} days")
    
    if info_items:
        html += f"<div class='progress'>"
        html += f"<p><strong>Information collected:</strong></p>"
        html += f"<p>{' • '.join(info_items)}</p>"
        html += f"</div>"
    
    html += f"</div>"
    return html
