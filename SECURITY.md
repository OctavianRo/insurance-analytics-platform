# Security

Use synthetic data for public examples. Never commit medical records, client files,
credentials, model artifacts trained on private records, Terraform state or tracking stores.

The API and dashboard are local research tools with no built-in user authentication.
Use an authenticated gateway, appropriate logging controls, data access boundaries and
model governance before any hosted deployment. Do not load serialized models or
Metaflow artifacts from untrusted sources.

Report suspected issues privately through the repository owner's GitHub profile.
Do not include sensitive sample records in public issues.
