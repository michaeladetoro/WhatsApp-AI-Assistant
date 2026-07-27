import argparse
import logging
import shutil
import sys
from pathlib import Path

# Ensure project root is on the Python path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from brain.config import FAISS_INDEX_PATH, KNOWLEDGE_DIR
from brain.kb_manager import KBManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("build_index")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the EndowBot FAISS knowledge base index."
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to a single .txt or .md file to add to the index.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete the existing index before rebuilding.",
    )
    args = parser.parse_args()

    index_path = Path(FAISS_INDEX_PATH)
    kb = KBManager()

    if args.clear and index_path.exists():
        shutil.rmtree(index_path)
        logger.info(f"Cleared existing index at {index_path}")

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        try:
            text = file_path.read_text(encoding="utf-8")
            count = kb.add_document(content=text, title=file_path.name, source_label=file_path.name)
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            sys.exit(1)
        print(f"\n✅ Added {count} chunks from '{file_path.name}' to the index.")
    else:
        if not KNOWLEDGE_DIR.exists():
            logger.error(f"Knowledge directory not found: {KNOWLEDGE_DIR}")
            logger.error(
                "Create data/knowledge/ and add .txt or .md files, then run this script."
            )
            sys.exit(1)

        count = kb.rebuild_from_files()
        if count == 0:
            print(
                f"\n⚠️  No documents found in {KNOWLEDGE_DIR}. Add .txt or .md files and try again."
            )
        else:
            print(f"\n✅ Index built successfully — {count} chunks indexed.")
            print(f"   Index saved to: {FAISS_INDEX_PATH}")
            print(
                "\nThe bot will use this index on the next startup (or call rag_handler.reload_index())."
            )


if __name__ == "__main__":
    main()
