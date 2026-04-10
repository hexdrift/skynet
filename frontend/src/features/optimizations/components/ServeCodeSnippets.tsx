"use client";

/**
 * Code snippet panel for the serve playground tab — renders a read-only
 * editor with language switcher (cURL/Python/JS/Go/DSPy).
 *
 * Extracted from app/optimizations/[id]/page.tsx. Isolates the language
 * tab state from the heavy parent.
 */

import { useState } from "react";
import dynamic from "next/dynamic";
import type { ServeInfoResponse } from "@/lib/types";
import { LangPicker } from "./ui-primitives";

const CodeEditor = dynamic(() => import("@/components/code-editor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="h-[180px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" />
  ),
});

export function ServeCodeSnippets({
  serveInfo,
  optimizationId,
}: {
  serveInfo: ServeInfoResponse;
  optimizationId: string;
}) {
  const [codeTab, setCodeTab] = useState<"curl" | "python" | "javascript" | "go" | "dspy">("curl");
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const url = `${apiBase}/serve/${optimizationId}`;
  const inputsObj = serveInfo.input_fields.map((f) => `"${f}": "<${f}>"`).join(", ");
  const inputsJson = JSON.stringify({
    inputs: Object.fromEntries(serveInfo.input_fields.map((f) => [f, `<${f}>`])),
  });
  const snippets = {
    curl: [
      `# Send a POST request to the optimized program endpoint`,
      `# Replace <field> placeholders with your actual input values`,
      `curl -X POST ${url} \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -d '${inputsJson}'`,
    ].join("\n"),
    python: [
      `import requests`,
      ``,
      `# Call the optimized program via the REST API`,
      `response = requests.post(`,
      `    "${url}",`,
      `    json={"inputs": {${inputsObj}}},`,
      `)`,
      ``,
      `# Parse and print the results`,
      `result = response.json()`,
      ...serveInfo.output_fields.map((f) => `print(result["outputs"]["${f}"])`),
    ].join("\n"),
    javascript: [
      `// Call the optimized program via fetch`,
      `const response = await fetch("${url}", {`,
      `  method: "POST",`,
      `  headers: { "Content-Type": "application/json" },`,
      `  body: JSON.stringify({ inputs: { ${serveInfo.input_fields.map((f) => `${f}: "<${f}>"`).join(", ")} } }),`,
      `});`,
      ``,
      `// Parse and use the results`,
      `const result = await response.json();`,
      ...serveInfo.output_fields.map((f) => `console.log(result.outputs.${f});`),
    ].join("\n"),
    go: [
      `package main`,
      ``,
      `import (`,
      `\t"bytes"`,
      `\t"encoding/json"`,
      `\t"fmt"`,
      `\t"net/http"`,
      `)`,
      ``,
      `func main() {`,
      `\t// Build the request payload`,
      `\tpayload, _ := json.Marshal(map[string]any{`,
      `\t\t"inputs": map[string]string{`,
      ...serveInfo.input_fields.map((f) => `\t\t\t"${f}": "<${f}>",`),
      `\t\t},`,
      `\t})`,
      ``,
      `\t// Send POST request to the optimized program`,
      `\tresp, _ := http.Post("${url}", "application/json", bytes.NewReader(payload))`,
      `\tdefer resp.Body.Close()`,
      ``,
      `\t// Decode the response`,
      `\tvar result map[string]any`,
      `\tjson.NewDecoder(resp.Body).Decode(&result)`,
      `\toutputs := result["outputs"].(map[string]any)`,
      ...serveInfo.output_fields.map((f) => `\tfmt.Println(outputs["${f}"])`),
      `}`,
    ].join("\n"),
    dspy: [
      `import dspy`,
      `import base64, pickle, requests`,
      ``,
      `# Download the optimized program artifact`,
      `artifact = requests.get(`,
      `    "${apiBase}/optimizations/${optimizationId}/artifact"`,
      `).json()`,
      ``,
      `# Deserialize the compiled program from the artifact`,
      `program = pickle.loads(`,
      `    base64.b64decode(artifact["program_artifact"]["program_pickle_base64"])`,
      `)`,
      ``,
      `# Configure your language model and run the program`,
      `lm = dspy.LM("gpt-4o-mini")`,
      `with dspy.context(lm=lm):`,
      `    result = program(${serveInfo.input_fields.map((f) => `${f}="<${f}>"`).join(", ")})`,
      ...serveInfo.output_fields.map((f) => `    print(result.${f})`),
    ].join("\n"),
  };
  const labels = {
    curl: "cURL",
    python: "Python",
    javascript: "JavaScript",
    go: "Go",
    dspy: "DSPy",
  } as const;
  const snippet = snippets[codeTab];
  return (
    <CodeEditor
      value={snippet}
      onChange={() => {}}
      height={`${(snippet.split("\n").length + 1) * 19.6 + 8}px`}
      readOnly
      label={<LangPicker value={codeTab} onChange={setCodeTab} labels={labels} />}
    />
  );
}
