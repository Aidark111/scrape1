"""
Step 3: NLP processing — VADER sentiment, TF-IDF keyword extraction, competitor detection.
Goal: Extract linguistic context (sentiment and key topics) for growth analysis.

Reads from: output/step2_features/ (Featurized data)
Writes to: output/step3_nlp/ (NLP-enriched data)

NLP Techniques:
- Sentiment: VADER (Rule-based lexical analyzer calibrated for social media context)
- Keywords: TF-IDF (Term Frequency-Inverse Document Frequency) to find unique post indicators
- Correlative analysis: Finds which keywords correlate statistically with high upvotes/views
- Competitor detection: Case-insensitive mention mapping (e.g., 'gpt' → 'GPT-4')
"""
import os
import pandas as pd
import numpy as np

import nltk
# VADER requires a specific lexicon data file for sentiment scoring.
nltk.download("vader_lexicon", quiet=True)
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

# Resolve paths relative to the lab/stage1 directory
STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(STAGE1_DIR, "output", "step2_features")
OUT_DIR = os.path.join(STAGE1_DIR, "output", "step3_nlp")
os.makedirs(OUT_DIR, exist_ok=True)


def add_sentiment(df, text_col="title_clean"):
    """
    Computes VADER sentiment metrics.
    - Compound score: Range [-1, 1], the primary metric for overall positivity.
    - Labels: Categorizes compound scores into 'Positive' (>=0.05), 'Negative' (<=-0.05), or 'Neutral'.
    """
    sia = SentimentIntensityAnalyzer()
    
    # POLARITY SCORING (Handles negation, irony, and social media jargon)
    scores = df[text_col].fillna("").apply(sia.polarity_scores)
    
    # Store individual metric components
    df["sentiment_compound"] = scores.apply(lambda s: s["compound"])
    df["sentiment_pos"] = scores.apply(lambda s: s["pos"])
    df["sentiment_neg"] = scores.apply(lambda s: s["neg"])
    
    # Broad classification: useful for grouping charts in stage2
    df["sentiment_label"] = df["sentiment_compound"].apply(
        lambda c: "Positive" if c >= 0.05 else ("Negative" if c <= -0.05 else "Neutral")
    )
    return df


def extract_keywords(df, text_col="title_clean", top_n=5):
    """
    Uses TF-IDF to extract the most descriptive keywords from each post.
    - Corpus-level: Analyzes which terms drive the highest engagement.
    - Per-post: Picks the top 5 terms with the highest localized TF-IDF score.
    """
    titles = df[text_col].fillna("").tolist()
    if len(titles) < 10:
        # TF-IDF requires a minimum document count to be statistically meaningful.
        df["top_keywords"] = ""
        return df

    # TF-IDF VECTORIZATION
    # - max_features=1000: limits to most common tokens to prevent memory blowout
    # - min_df=3: ignores unique typos/rare words
    # - ngram_range=(1, 2): captures both single words and two-word phrases (e.g. 'claude output')
    tfidf = TfidfVectorizer(
        max_features=1000, stop_words="english",
        min_df=3, ngram_range=(1, 2),
    )
    X = tfidf.fit_transform(titles)
    feature_names = tfidf.get_feature_names_out()

    # Per-row keyword extraction
    keywords_list = []
    for i in range(X.shape[0]):
        row = X[i].toarray().ravel()
        # Sort terms by localized score (high score = word is common in this post but rare in others)
        top_idx = row.argsort()[-top_n:][::-1]
        top_words = [feature_names[j] for j in top_idx if row[j] > 0]
        keywords_list.append("|".join(top_words))

    df["top_keywords"] = keywords_list

    # ENGAGEMENT CORRELATION ANALYSIS
    # Finds which specific keywords actually predict viral success (Pearson Correlation).
    engagement_col = None
    for col in ["engagement_score", "upvotes", "views", "likes"]:
        if col in df.columns:
            engagement_col = col
            break

    if engagement_col:
        engagement = df[engagement_col].values
        correlations = {}
        for j in range(X.shape[1]):
            col_vals = X[:, j].toarray().ravel()
            if col_vals.sum() > 0:
                # Correlation coefficient: +1 = term predicts viral success, -1 = term predicts failure
                correlations[feature_names[j]] = np.corrcoef(col_vals, engagement)[0, 1]

        # Log identifying keywords for manual verification
        sorted_kw = sorted(correlations.items(), key=lambda x: x[1], reverse=True)
        viral_kw = [w for w, c in sorted_kw[:20] if c > 0]
        low_kw = [w for w, c in sorted_kw[-20:] if c < 0]
        print(f"    Top viral keywords: {', '.join(viral_kw[:10])}")
        print(f"    Low engagement keywords: {', '.join(low_kw[:10])}")

    return df


def detect_competitors(df, text_col="title_clean"):
    """
    Identifies mentions of competing AI models and specific Claude features.
    - Maps diverse nicknames/slang to standardized names (e.g. 'gpt-4o' → 'GPT-4o').
    - Sets a categorical flag 'mentions_competitor' for competitive analysis.
    """
    competitors = {
        "chatgpt": "ChatGPT", "gpt-4": "GPT-4", "gpt4": "GPT-4", "gpt-4o": "GPT-4o",
        "openai": "OpenAI", "gemini": "Gemini", "bard": "Bard",
        "copilot": "Copilot", "deepseek": "DeepSeek", "llama": "Llama",
        "mistral": "Mistral", "grok": "Grok", "perplexity": "Perplexity",
    }
    features = {
        "artifacts": "Artifacts", "sonnet": "Sonnet", "opus": "Opus",
        "haiku": "Haiku", "claude code": "Claude Code", "mcp": "MCP",
        "computer use": "Computer Use", "extended thinking": "Extended Thinking",
    }

    # Helper functions for pattern matching (mapped via standardize list)
    def find_mentions(text):
        t = str(text).lower()
        found = [name for kw, name in competitors.items() if kw in t]
        return "|".join(found) if found else ""

    def find_features(text):
        t = str(text).lower()
        found = [name for kw, name in features.items() if kw in t]
        return "|".join(found) if found else ""

    # Generate detection columns
    df["competitors_mentioned"] = df[text_col].apply(find_mentions)
    df["features_mentioned"] = df[text_col].apply(find_features)
    df["mentions_competitor"] = df["competitors_mentioned"].str.len() > 0

    return df


def process_platform(name, df):
    """ Sequentially applies NLP transformations to a single platform's dataframe. """
    print(f"\n  Processing {name}...")

    # Calculate VADER sentiment
    print(f"    Running VADER sentiment...")
    df = add_sentiment(df)
    pos = (df["sentiment_label"] == "Positive").sum()
    neg = (df["sentiment_label"] == "Negative").sum()
    neu = (df["sentiment_label"] == "Neutral").sum()
    print(f"    Sentiment: {pos} pos, {neu} neu, {neg} neg "
          f"(mean={df['sentiment_compound'].mean():.3f})")

    # Extract top keywords per post
    print(f"    Extracting TF-IDF keywords...")
    df = extract_keywords(df)

    # Detect competitor/feature mentions
    print(f"    Detecting competitors and features...")
    df = detect_competitors(df)
    n_comp = df["mentions_competitor"].sum()
    print(f"    {n_comp} posts mention competitors ({n_comp/len(df)*100:.1f}%)")

    return df


def main():
    """ Orstrates NLP processing for all supported platforms. """
    print("=" * 60)
    print("STEP 3: NLP PROCESSING")
    print("=" * 60)

    # Process all available platforms produced in step2
    for name in ["reddit", "youtube", "twitter"]:
        in_path = os.path.join(IN_DIR, f"{name}_features.csv")
        if not os.path.exists(in_path):
            print(f"\n  {name}: no feature data, skipping")
            continue

        df = pd.read_csv(in_path, encoding="utf-8")
        df = process_platform(name, df)

        # Output to final step staging area for LLM processing (step4)
        out_path = os.path.join(OUT_DIR, f"{name}_nlp.csv")
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  Saved: {out_path} ({len(df)} rows, {len(df.columns)} cols)")

    print(f"\n{'=' * 60}")
    print(f"STEP 3 DONE — outputs in {OUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
