import re
from pathlib import Path

def paste_response(response_content):
    """
    Parses a response containing code blocks and writes them to files,
    handling both absolute and relative paths safely.

    Args:
        response_content (str): The string response from the LLM.
    """
    pattern = re.compile(
        r"<file_path:([^>]+?)>\s*```(?:.*?)\n(.*?)\n```",
        re.DOTALL | re.MULTILINE
    )

    matches = pattern.finditer(response_content)
    files_processed = 0
    found_matches = False

    for match in matches:
        found_matches = True
        file_path_str = match.group(1).strip()
        code_content = match.group(2)

        if not file_path_str:
            print("Warning: Found a code block with an empty file path. Skipping.")
            continue

        print(f"Found path in response: '{file_path_str}'")
        raw_path = Path(file_path_str)
        
        # Determine the final target path.
        # If the path from the LLM is absolute, use it directly.
        # If it's relative, resolve it against the current working directory.
        if raw_path.is_absolute():
            target_path = raw_path
        else:
            target_path = Path.cwd() / raw_path

        # Normalize the path to resolve any ".." or "." segments.
        target_path = target_path.resolve()

        try:
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # If file exists, compare content to avoid unnecessary overwrites
            if target_path.exists():
                with open(target_path, 'r', encoding='utf-8') as existing_file:
                    if existing_file.read() == code_content:
                        print(f"  -> No changes for '{target_path}', skipping.")
                        continue

            # Write the extracted code to the file
            with open(target_path, 'w', encoding='utf-8') as outfile:
                outfile.write(code_content)

            print(f"  -> Wrote {len(code_content)} bytes to '{target_path}'")
            files_processed += 1

        except OSError as e:
            print(f"  -> Error writing file '{target_path}': {e}")
        except Exception as e:
            print(f"  -> An unexpected error occurred for file '{target_path}': {e}")

    if not found_matches:
        print("\nNo file paths and code blocks matching the expected format were found in the response.")
    elif files_processed > 0:
        print(f"\nSuccessfully processed {files_processed} file(s).")
    else:
        print("\nFound matching blocks, but no files were written.")