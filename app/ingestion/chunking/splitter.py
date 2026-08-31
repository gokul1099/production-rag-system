from typing import List
import logfire

def chunk_text(text: str, chunk_size:int = 1500) -> List[str]:
    """
    Simple sematic-ish chunker that splits by paragraphs.
    Ensures chunks do not excess the specified size.
    """

    with logfire.span("Text chunking", text_length=len(text)):
        if not text.strip():
            return []

        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for p in paragraphs:
            if len(current_chunk) + len(p) < chunk_size:
                current_chunk += p + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = p + "\n\n"
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        valid_chunk = [c for c in chunks if c.strip()]
        logfire.info(f"Generated {len(valid_chunk)} chunks")
        return valid_chunk
