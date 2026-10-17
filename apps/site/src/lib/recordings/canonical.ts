/**
 * Canonical form of a recording, byte-identical to the exporter's
 * `json-sorted-compact/1` (Python json.dumps(sort_keys=True, separators=(",", ":"),
 * ensure_ascii=False)). Numbers keep their original lexeme: JSON.parse would turn the
 * exporter's "1.0" into 1 and change the hash.
 */

class RawNumber {
  constructor(readonly text: string) {}
}

type Node = null | boolean | string | RawNumber | Node[] | { [key: string]: Node };

const NUMBER = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
const STRING = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/y;
const SPACE = /[ \t\n\r]*/y;

class Parser {
  private at = 0;

  constructor(private readonly text: string) {}

  parse(): Node {
    const value = this.value();
    this.skip();
    if (this.at !== this.text.length) this.fail("trailing content");
    return value;
  }

  private skip() {
    SPACE.lastIndex = this.at;
    SPACE.exec(this.text);
    this.at = SPACE.lastIndex;
  }

  private fail(message: string): never {
    throw new SyntaxError(`${message} at offset ${this.at}`);
  }

  private match(pattern: RegExp): string | null {
    pattern.lastIndex = this.at;
    const found = pattern.exec(this.text);
    if (!found) return null;
    this.at = pattern.lastIndex;
    return found[0];
  }

  private literal(word: string): boolean {
    if (!this.text.startsWith(word, this.at)) return false;
    this.at += word.length;
    return true;
  }

  private value(): Node {
    this.skip();
    const char = this.text[this.at];
    if (char === "{") return this.object();
    if (char === "[") return this.array();
    if (char === '"') return this.string();
    if (this.literal("true")) return true;
    if (this.literal("false")) return false;
    if (this.literal("null")) return null;
    const number = this.match(NUMBER);
    if (number !== null) return new RawNumber(number);
    return this.fail("unexpected token");
  }

  private string(): string {
    const raw = this.match(STRING);
    if (raw === null) this.fail("invalid string");
    return JSON.parse(raw) as string;
  }

  private array(): Node[] {
    this.at += 1;
    const items: Node[] = [];
    this.skip();
    if (this.literal("]")) return items;
    for (;;) {
      items.push(this.value());
      this.skip();
      if (this.literal("]")) return items;
      if (!this.literal(",")) this.fail("expected , or ]");
    }
  }

  private object(): { [key: string]: Node } {
    this.at += 1;
    const entries: { [key: string]: Node } = {};
    this.skip();
    if (this.literal("}")) return entries;
    for (;;) {
      this.skip();
      const key = this.string();
      if (Object.hasOwn(entries, key)) this.fail(`duplicate key ${key}`);
      this.skip();
      if (!this.literal(":")) this.fail("expected :");
      entries[key] = this.value();
      this.skip();
      if (this.literal("}")) return entries;
      if (!this.literal(",")) this.fail("expected , or }");
    }
  }
}

function serialize(node: Node): string {
  if (node instanceof RawNumber) return node.text;
  if (Array.isArray(node)) return `[${node.map(serialize).join(",")}]`;
  if (node !== null && typeof node === "object") {
    const keys = Object.keys(node).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${serialize(node[key])}`).join(",")}}`;
  }
  return JSON.stringify(node);
}

/** Canonical text of the document without its `integrity` block (what is hashed). */
export function canonicalBody(text: string): string {
  const root = new Parser(text).parse();
  if (root === null || typeof root !== "object" || Array.isArray(root) || root instanceof RawNumber) {
    throw new SyntaxError("a recording must be a JSON object");
  }
  const body = Object.fromEntries(Object.entries(root).filter(([key]) => key !== "integrity"));
  return serialize(body);
}
