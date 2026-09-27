from pathlib import Path
from docx import Document
from pypdf import PdfReader
from src.project_paths import KNOWLEDGE_PROCESSED_DIR, KNOWLEDGE_SOURCE_DIR


RAW_DIR = KNOWLEDGE_SOURCE_DIR
PROCESSED_DIR = KNOWLEDGE_PROCESSED_DIR


def read_docx(path: Path) -> str:
    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text.strip())
    return "\n".join(texts)


def save_text(name: str, content: str):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{name}.txt"
    out_path.write_text(content, encoding="utf-8")


def main():
    for path in RAW_DIR.iterdir():
        if path.suffix.lower() == ".docx":
            text = read_docx(path)
            save_text(path.stem, text)
            print(f"[DOCX] processed: {path.name}")

        elif path.suffix.lower() == ".pdf":
            text = read_pdf(path)
            save_text(path.stem, text)
            print(f"[PDF] processed: {path.name}")

        else:
            print(f"[SKIP] unsupported: {path.name}")


if __name__ == "__main__":
    main()
