TRADFRI_SCHEMA = {
    "type": "array",
    "items": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "fw_image_type": {"type": "integer"},
                    "fw_type": {"type": "integer"},
                    "fw_sha3_256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "fw_binary_url": {"type": "string", "format": "uri"},
                },
                "required": [
                    "fw_image_type",
                    "fw_type",
                    "fw_sha3_256",
                    "fw_binary_url",
                ],
            },
            {
                "type": "object",
                "properties": {
                    "fw_update_prio": {"type": "integer"},
                    "fw_filesize": {"type": "integer"},
                    "fw_type": {"type": "integer"},
                    "fw_hotfix_version": {"type": "integer"},
                    "fw_major_version": {"type": "integer"},
                    "fw_binary_checksum": {
                        "type": "string",
                        "pattern": "^[a-f0-9]{128}$",
                    },
                    "fw_minor_version": {"type": "integer"},
                    "fw_sha3_256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "fw_binary_url": {"type": "string", "format": "uri"},
                },
                "required": [
                    "fw_update_prio",
                    "fw_filesize",
                    "fw_type",
                    "fw_hotfix_version",
                    "fw_major_version",
                    "fw_binary_checksum",
                    "fw_minor_version",
                    "fw_sha3_256",
                    "fw_binary_url",
                ],
            },
            # Old IKEA format (new gateway)
            {
                "type": "object",
                "properties": {
                    "fw_binary_url": {"type": "string", "format": "uri"},
                    "fw_filesize": {"type": "integer"},
                    "fw_hotfix_version": {"type": "integer"},
                    "fw_major_version": {"type": "integer"},
                    "fw_minor_version": {"type": "integer"},
                    "fw_req_hotfix_version": {"type": "integer"},
                    "fw_req_major_version": {"type": "integer"},
                    "fw_req_minor_version": {"type": "integer"},
                    "fw_type": {"const": 0},
                    "fw_update_prio": {"type": "integer"},
                    "fw_weblink_relnote": {"type": "string", "format": "uri"},
                },
                "required": [
                    "fw_binary_url",
                    "fw_filesize",
                    "fw_hotfix_version",
                    "fw_major_version",
                    "fw_minor_version",
                    "fw_req_hotfix_version",
                    "fw_req_major_version",
                    "fw_req_minor_version",
                    "fw_type",
                    "fw_update_prio",
                    "fw_weblink_relnote",
                ],
            },
            # Old IKEA format (device)
            {
                "type": "object",
                "properties": {
                    "fw_binary_url": {"type": "string", "format": "uri"},
                    "fw_file_version_LSB": {"type": "integer"},
                    "fw_file_version_MSB": {"type": "integer"},
                    "fw_filesize": {"type": "integer"},
                    "fw_image_type": {"type": "integer"},
                    "fw_manufacturer_id": {"type": "integer"},
                    "fw_type": {"const": 2},
                },
                "required": [
                    "fw_binary_url",
                    "fw_file_version_LSB",
                    "fw_file_version_MSB",
                    "fw_filesize",
                    "fw_image_type",
                    "fw_manufacturer_id",
                    "fw_type",
                ],
            },
            # Old IKEA format (old gateway)
            {
                "type": "object",
                "properties": {
                    "fw_binary_url": {"type": "string", "format": "uri"},
                    "fw_build_version": {"type": "integer"},
                    "fw_file_version_LSB": {"type": "integer"},
                    "fw_file_version_MSB": {"type": "integer"},
                    "fw_filesize": {"type": "integer"},
                    "fw_hotfix_version": {"type": "integer"},
                    "fw_image_type": {"type": "integer"},
                    "fw_major_version": {"type": "integer"},
                    "fw_manufacturer_id": {"type": "integer"},
                    "fw_minor_version": {"type": "integer"},
                    "fw_type": {"const": 1},
                },
                "required": [
                    "fw_binary_url",
                    "fw_build_version",
                    "fw_file_version_LSB",
                    "fw_file_version_MSB",
                    "fw_filesize",
                    "fw_hotfix_version",
                    "fw_image_type",
                    "fw_major_version",
                    "fw_manufacturer_id",
                    "fw_minor_version",
                    "fw_type",
                ],
            },
        ]
    },
}

LEDVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "firmwares": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "blob": {"type": ["null", "string"]},
                    "identity": {
                        "type": "object",
                        "properties": {
                            "company": {"type": "integer"},
                            "product": {"type": "integer"},
                            "version": {
                                "type": "object",
                                "properties": {
                                    "major": {"type": "integer"},
                                    "minor": {"type": "integer"},
                                    "build": {"type": "integer"},
                                    "revision": {"type": "integer"},
                                },
                                "required": ["major", "minor", "build", "revision"],
                            },
                        },
                        "required": ["company", "product", "version"],
                    },
                    "releaseNotes": {"type": "string"},
                    "shA256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "name": {"type": "string"},
                    "productName": {"type": "string"},
                    "fullName": {"type": "string"},
                    "extension": {"type": "string"},
                    "released": {"type": "string", "format": "date-time"},
                    "salesRegion": {"type": ["string", "null"]},
                    "length": {"type": "integer"},
                },
                "required": [
                    "blob",
                    "identity",
                    "releaseNotes",
                    "shA256",
                    "name",
                    "productName",
                    "fullName",
                    "extension",
                    "released",
                    "salesRegion",
                    "length",
                ],
            },
        }
    },
    "required": ["firmwares"],
}

SALUS_SCHEMA = {
    "type": "object",
    "properties": {
        "versions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "version": {
                        "type": "string",
                        "pattern": "^(|[0-9A-F]{8}|[0-9A-F]{12})$",
                    },
                    "url": {"type": "string", "format": "uri"},
                },
                "required": ["model", "version", "url"],
            },
        }
    },
    "required": ["versions"],
}

SONOFF_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "fw_binary_url": {"type": "string", "format": "uri"},
            "fw_file_version": {"type": "integer"},
            "fw_filesize": {"type": "integer"},
            "fw_image_type": {"type": "integer"},
            "fw_manufacturer_id": {"type": "integer"},
            "model_id": {"type": "string"},
        },
        "required": [
            "fw_binary_url",
            "fw_file_version",
            "fw_filesize",
            "fw_image_type",
            "fw_manufacturer_id",
            "model_id",
        ],
    },
}

INOVELLI_SCHEMA = {
    "type": "object",
    "patternProperties": {
        "^[A-Z0-9_-]+$": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "version": {
                        "type": "string",
                        "pattern": "^(?:[0-9A-F]{8}|[0-9]+)$",
                    },
                    "channel": {"type": "string"},
                    "firmware": {"type": "string", "format": "uri"},
                    "manufacturer_id": {"type": "integer"},
                    "image_type": {"type": "integer"},
                },
                "required": [
                    "version",
                    "channel",
                    "firmware",
                    "manufacturer_id",
                    "image_type",
                ],
            },
        }
    },
}

THIRD_REALITY_SCHEMA = {
    "type": "object",
    "properties": {
        "versions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "modelId": {"type": "string"},
                    "url": {"type": "string", "format": "uri"},
                    "version": {
                        "type": "string",
                        "pattern": "^\\d+\\.\\d+\\.\\d+$",
                    },
                    "imageType": {"type": "integer"},
                    "manufacturerId": {"type": "integer"},
                    "fileVersion": {"type": "integer"},
                },
                "required": [
                    "modelId",
                    "url",
                    "version",
                    "imageType",
                    "manufacturerId",
                    "fileVersion",
                ],
            },
        }
    },
    "required": ["versions"],
}

REMOTE_PROVIDER_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "firmwares": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "binary_url": {"type": "string", "format": "uri"},
                    "path": {"type": "string"},
                    "file_version": {"type": "integer"},
                    "file_size": {"type": "integer"},
                    "image_type": {"type": "integer"},
                    "manufacturer_names": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "model_names": {"type": "array", "items": {"type": "string"}},
                    "manufacturer_id": {"type": "integer"},
                    "changelog": {"type": "string"},
                    "release_notes": {"type": "string"},
                    "checksum": {
                        "type": "string",
                        "pattern": "^sha3-256:[a-f0-9]{64}$",
                    },
                    "min_hardware_version": {"type": "integer"},
                    "max_hardware_version": {"type": "integer"},
                    "min_current_file_version": {"type": "integer"},
                    "max_current_file_version": {"type": "integer"},
                    "specificity": {"type": "integer"},
                },
                "required": [
                    # "binary_url",
                    # "path",
                    "file_version",
                    "file_size",
                    "image_type",
                    # "manufacturer_names",
                    # "model_names",
                    "manufacturer_id",
                    # "changelog",
                    "checksum",
                    # "min_hardware_version",
                    # "max_hardware_version",
                    # "min_current_file_version",
                    # "max_current_file_version",
                    # "release_notes",
                    # "specificity",
                ],
            },
        }
    },
    "required": ["firmwares"],
}

Z2M_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "fileVersion": {"type": "integer"},
            "fileSize": {"type": "integer"},
            "manufacturerCode": {"type": "integer"},
            "imageType": {"type": "integer"},
            "sha512": {"type": "string", "pattern": "^[a-f0-9]{128}$"},
            "url": {"type": "string", "format": "uri"},
            "path": {"type": "string"},
            "minFileVersion": {"type": "integer"},
            "maxFileVersion": {"type": "integer"},
            "manufacturerName": {"type": "array", "items": {"type": "string"}},
            "modelId": {"type": "string"},
        },
        "required": [
            "fileVersion",
            "fileSize",
            "manufacturerCode",
            "imageType",
            "sha512",
            "url",
        ],
    },
}
