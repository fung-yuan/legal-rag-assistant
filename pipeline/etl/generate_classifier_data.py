import os
import re
import pandas as pd

INPUT_CSV = "data/etl_intermediate/moroccan_law_pages_cleaned.csv"
OUTPUT_CSV = "data/etl_intermediate/labeled_article_context.csv"

def main():
    print("Generating training dataset for article classification...")
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found! Run the initial pipeline steps first.")
        return

    # Load cleaned pages dataset
    df = pd.read_csv(INPUT_CSV, encoding="utf-8")
    df["Clean_Content"] = df["Clean_Content"].fillna("")
    print(f"Loaded {len(df)} pages of corpus.")

    article_pattern = re.compile(
        r'\b(article\s+premier|art\.\s*\d+|article\s*\d+)\b',
        re.IGNORECASE
    )

    samples = []
    
    # Process French pages to extract context windows
    for _, row in df.iterrows():
        if row.get("Language") != "FR":
            continue
        text = str(row["Clean_Content"])
        if not text.strip():
            continue

        for m in article_pattern.finditer(text):
            # Extract 50 characters window before/after the match
            start_pos = max(0, m.start() - 50)
            end_pos = min(len(text), m.end() + 50)
            context = text[start_pos:end_pos].replace("\n", " ").strip()
            
            # Context before the match for labeling heuristic
            prefix = text[max(0, m.start() - 15):m.start()].lower().strip()
            suffix = text[m.end():min(len(text), m.end() + 25)].lower().strip()
            
            match_text = m.group(0)
            
            # Rule 1: Lowercase mention inside sentence is a reference
            if not match_text[0].isupper():
                label = 0
            # Rule 2: Preceded by preposition is a reference
            elif (prefix.endswith("l'") or prefix.endswith("d'") or 
                  prefix.endswith("les") or prefix.endswith("des") or 
                  prefix.endswith("de") or prefix.endswith("à") or 
                  prefix.endswith("dans") or prefix.endswith("sur") or 
                  prefix.endswith("aux")):
                label = 0
            # Rule 3: Capitalized and preceded by newline, period, or footnote is a definition
            elif (prefix == "" or prefix.endswith(".") or prefix.endswith(":") or 
                  prefix.endswith(",") or prefix[-1:].isdigit() or prefix.endswith("»") or
                  prefix.endswith(" - ") or prefix.endswith("\n")):
                # Check for reference indicators in the suffix (like "ci-dessus", "précité")
                if any(x in suffix for x in ["ci-dessus", "ci-dessous", "précité", "précitée", "du présent", "de la présente"]):
                    label = 0
                else:
                    label = 1
            else:
                continue

            samples.append({
                "context": context,
                "label": label
            })

            # Cap samples to keep training dataset balanced and small
            if len(samples) >= 1500:
                break
        if len(samples) >= 1500:
            break

    # Save labeled dataset
    out_df = pd.DataFrame(samples)
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Successfully saved {len(out_df)} labeled contexts to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
