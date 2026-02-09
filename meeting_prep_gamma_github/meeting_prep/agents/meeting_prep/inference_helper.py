def _get_relevant_solved_challenges(csv_text: str, research_text: str) -> str:
    """
    Parses the solved challenges CSV and filters for the most relevant industry based on research text.
    """
    if not csv_text or not csv_text.strip():
        return ""

    # 1. Define Industry Keywords Mapping
    # industries found: Financial Services, Manufacturing/Logistics, Media/Streaming, Online Travel, Retail/eCommerce, SaaS/Technology, Startup
    industry_keywords = {
        "Retail/eCommerce": ["retail", "ecommerce", "e-commerce", "shopping", "store", "merchandise", "consumer", "goods"],
        "Financial Services": ["bank", "finance", "financial", "fintech", "insurance", "investment", "payment", "wealth", "capital"],
        "Manufacturing/Logistics": ["manufacturing", "logistics", "supply chain", "shipping", "freight", "transport", "production", "industrial"],
        "Media/Streaming": ["media", "streaming", "entertainment", "broadcasting", "content", "video", "music", "gaming"],
        "Online Travel": ["travel", "booking", "flight", "hotel", "accommodation", "tourism", "vacation"],
        "SaaS/Technology": ["saas", "technology", "software", "cloud", "platform", "tech", "digital", "app"],
        "Startup": ["startup", "scaleup", "venture", "growth", "early stage"]
    }

    # 2. Infer Industry from Research Text
    text_lower = research_text.lower()
    scores = {ind: 0 for ind in industry_keywords}
    
    for industry, keywords in industry_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                scores[industry] += text_lower.count(keyword)
    
    # Get top scoring industry
    best_industry = max(scores, key=scores.get)
    if scores[best_industry] == 0:
        logger.warning("Could not infer industry from research text. Defaulting to all (capped).")
        target_industry = None # No specific filter
    else:
        logger.info(f"Inferred Industry: {best_industry} (Score: {scores[best_industry]})")
        target_industry = best_industry

    # 3. Parse CSV and Filter
    output_lines = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        count = 0
        for row in reader:
            # Check industry match
            row_industry = row.get("industry", "").strip()
            
            # Simple inclusion check (e.g. "Retail" matches "Retail/eCommerce") logic? 
            # Actually CSV values are exact matches like "Retail/eCommerce"
            
            if target_industry and row_industry != target_industry:
                continue
                
            # Formatting the output
            # Columns: "industry","customer_info","problem_overview","challenge","product","capability","solution", "reference"
            customer = row.get("customer_info", "N/A")
            challenge = row.get("challenge", "N/A")
            solution = row.get("solution", "N/A")
            product = row.get("product", "N/A")
            reference = row.get("reference", "N/A")
            
            output_lines.append(f"### Case Study: {customer}")
            output_lines.append(f"- **Industry**: {row_industry}")
            output_lines.append(f"- **Challenge**: {challenge}")
            output_lines.append(f"- **Solution ({product})**: {solution}")
            output_lines.append(f"- **Reference**: {reference}")
            output_lines.append("") # Spacer
            
            count += 1
            if count >= 30: # Safety cap to avoid huge prompt
                output_lines.append("... (List truncated for length)")
                break
                
        if not output_lines and target_industry:
             # Fallback if no exact matches found but industry was inferred? 
             # Should practically not happen if mapping is correct vs file content
             output_lines.append(f"No specific case studies found for inferred industry: {target_industry}")

    except Exception as e:
        logger.error(f"Error parsing solved challenges CSV: {e}")
        return f"Error processing Solved Challenges data: {e}"

    if not output_lines:
        return "No solved challenges data found."
        
    header = f"Relevant Solved Challenges (Inferred Industry: {target_industry if target_industry else 'All'})\n"
    return header + "\n" + "\n".join(output_lines)
