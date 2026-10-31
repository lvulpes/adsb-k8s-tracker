import json
import sys
import yaml

def json_to_yaml(json_path, yaml_path):
    # 1. Read the JSON file
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. Write to YAML (2 spaces for YAML output is PyYAML's default)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
            allow_unicode=True,
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage {sys.argv[0]} input.json output.yaml")
        exit()
    IN_FILE_NAME = sys.argv[1]
    OUT_FILE_NAME = sys.argv[2]
    json_to_yaml(IN_FILE_NAME, OUT_FILE_NAME)

