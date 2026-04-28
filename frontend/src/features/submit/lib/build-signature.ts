/**
 * Builds a DSPy Signature class template from a column-role map.
 * Columns marked "input" become InputFields; "output" → OutputFields.
 * Input columns flagged ``"image"`` in ``kinds`` are typed ``dspy.Image``
 * so vision-capable models receive the cell as an image instance — text
 * inputs (the default) stay typed ``str``. Column names are sanitized
 * to valid Python identifiers.
 */
export function buildSignatureTemplate(
  roles: Record<string, "input" | "output" | "ignore">,
  kinds: Record<string, "text" | "image"> = {},
): string {
  const inputs = Object.entries(roles)
    .filter(([, r]) => r === "input")
    .map(([c]) => c);
  const outputs = Object.entries(roles)
    .filter(([, r]) => r === "output")
    .map(([c]) => c);
  const toId = (s: string) => s.replace(/[^a-zA-Z0-9_\u0590-\u05FF]/g, "_").replace(/^(\d)/, "_$1");
  const inputType = (col: string) => (kinds[col] === "image" ? "dspy.Image" : "str");
  const inLines =
    inputs.length > 0
      ? inputs
          .map((c) => `    ${toId(c)}: ${inputType(c)} = dspy.InputField(desc="")`)
          .join("\n")
      : `    input_field: str = dspy.InputField(desc="")`;
  const outLines =
    outputs.length > 0
      ? outputs.map((c) => `    ${toId(c)}: str = dspy.OutputField(desc="")`).join("\n")
      : `    output_field: str = dspy.OutputField(desc="")`;
  return `class MySignature(dspy.Signature):\n    """Describe the task here."""\n\n    # inputs\n${inLines}\n\n    # outputs\n${outLines}\n`;
}
