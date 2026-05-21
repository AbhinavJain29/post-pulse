"""
AI feedback generator for LinkedIn posts using the Anthropic API (Claude).
Analyzes post content + metrics and returns structured improvement suggestions.
"""
import re
import anthropic


FEEDBACK_PROMPT = """You are a straight-talking content coach who reviews LinkedIn posts written by real people, for real people.

Your job is to make sure the post sounds genuinely human — the kind of thing a person would actually say to a colleague over coffee, not a press release or a motivational poster. People scroll fast and they can smell inauthenticity immediately.

---
POST CONTENT:
{content}

---
PERFORMANCE METRICS:
- Impressions: {impressions:,}
- Reactions: {reactions:,}
- Comments: {comments:,}
- Reposts: {reposts:,}
- Profile viewers from this post: {profile_viewers:,}
- Followers gained from this post: {followers_gained:,}

---
Review the post through these lenses and provide feedback in the following format:

## Overall Assessment
One honest sentence on how the post lands as a piece of human writing. Does it feel like a real person talking, or does it feel polished and hollow?

## What Worked
2-3 specific things that feel genuine, relatable, or compelling — moments where a real human voice comes through.

## What to Improve
Identify the distinct problem areas in this post. Group related issues into categories (e.g. "Hook", "Tone", "Structure", "Specificity", "Call to Action"). For each category:
- Name the category
- Explain the underlying problem once, clearly
- Give one concrete example of how to fix it in this specific post

Do not list the same tip more than once under different names. If two issues share the same root cause, group them. Aim for 2-4 categories, not a laundry list.

## Rewrite Suggestion
Rewrite the opening 2-3 lines so they sound like something a real person would say — conversational, specific, and worth reading. Avoid buzzwords, vague inspiration, and anything that sounds like it was written by a committee.

## Key Takeaway
One concrete lesson the writer should carry into their next post.

Be direct and honest. The goal is a post that a human wrote and that other humans genuinely want to read."""


class PostFeedbackGenerator:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate_feedback(self, post: dict) -> dict:
        """
        Generate AI feedback for a single post.
        Returns a dict with keys: overall_assessment, what_worked, what_to_improve,
        rewrite_suggestion, key_takeaway.
        """
        content = post.get("content", "").strip()
        if not content:
            empty = "_No post content available for analysis._"
            return {
                "overall_assessment": empty,
                "what_worked": "",
                "what_to_improve": "",
                "rewrite_suggestion": "",
                "key_takeaway": "",
            }

        prompt = FEEDBACK_PROMPT.format(
            content=content,
            impressions=post.get("impressions", 0),
            reactions=post.get("reactions", 0),
            comments=post.get("comments", 0),
            reposts=post.get("reposts", 0),
            profile_viewers=post.get("profile_viewers", 0),
            followers_gained=post.get("followers_gained", 0),
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        return _parse_sections(message.content[0].text.strip())

    def generate_batch_feedback(self, posts: list[dict], on_progress=None) -> list[dict]:
        """
        Generate feedback for a list of posts. Skips posts that already have
        'ai_feedback' set. Calls on_progress(posts) after each post if provided,
        so the caller can persist state incrementally.
        """
        total = len(posts)
        for i, post in enumerate(posts, 1):
            if post.get("ai_feedback"):
                print(f"  Skipping ({i}/{total}) — feedback already exists: {post.get('url', '')[:60]}...")
                continue
            print(f"  Generating AI feedback ({i}/{total}): {post.get('url', '')[:60]}...")
            try:
                post["ai_feedback"] = self.generate_feedback(post)
            except Exception as e:
                print(f"  Warning: AI feedback failed — {e}")
                post["ai_feedback"] = {
                    "overall_assessment": f"_Feedback generation failed: {e}_",
                    "what_worked": "",
                    "what_to_improve": "",
                    "rewrite_suggestion": "",
                    "key_takeaway": "",
                }
            if on_progress:
                on_progress(posts)
        return posts


def _parse_sections(text: str) -> dict:
    """
    Parse Claude's markdown response into a dict of named sections.
    Keys: overall_assessment, what_worked, what_to_improve, rewrite_suggestion, key_takeaway.
    """
    section_map = {
        "overall assessment": "overall_assessment",
        "what worked": "what_worked",
        "what to improve": "what_to_improve",
        "rewrite suggestion": "rewrite_suggestion",
        "key takeaway": "key_takeaway",
    }
    result = {v: "" for v in section_map.values()}

    # Split on ## headings
    parts = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for part in parts:
        if not part.strip():
            continue
        lines = part.split("\n", 1)
        heading = lines[0].strip().lower()
        body = lines[1].strip() if len(lines) > 1 else ""
        for label, key in section_map.items():
            if label in heading:
                result[key] = body
                break

    return result
