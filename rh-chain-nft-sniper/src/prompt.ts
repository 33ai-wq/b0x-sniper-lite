// Interactive prompt utilities
// Source: adapted from solotop999/opensea-nft-public-mint

import readline from "readline";
import chalk from "chalk";

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: true,
});

export function askText(question: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(chalk.cyan(` ${question}: `), (answer) => resolve(answer.trim()));
  });
}

export function askHidden(question: string): Promise<string> {
  return new Promise((resolve) => {
    const stdin = process.stdin;
    const stdout = process.stdout;

    stdout.write(chalk.cyan(` ${question}: `));
    stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding("utf8");

    let input = "";
    const onData = (char: Buffer) => {
      const c = char.toString();
      if (c === "\n" || c === "\r" || c === "\u0004") {
        stdout.write("\n");
        stdin.setRawMode(false);
        stdin.pause();
        stdin.removeListener("data", onData);
        resolve(input);
      } else if (c === "\u0003") {
        stdout.write("\n");
        stdin.setRawMode(false);
        stdin.pause();
        stdin.removeListener("data", onData);
        process.exit(1);
      } else if (c === "\b" || c === "\u007f") {
        if (input.length > 0) {
          input = input.slice(0, -1);
          stdout.write("\b \b");
        }
      } else {
        input += c;
        stdout.write("*");
      }
    };

    stdin.on("data", onData);
  });
}

export function askNumber(
  question: string,
  defaultValue: number,
  options: { min?: number; max?: number } = {}
): Promise<number> {
  const { min, max } = options;
  return new Promise((resolve) => {
    const prompt = max !== undefined
      ? `${question} [${defaultValue}] (${min}–${max}): `
      : min !== undefined
      ? `${question} [${defaultValue}] (min ${min}): `
      : `${question} [${defaultValue}]: `;

    rl.question(chalk.cyan(` ${prompt}`), (answer) => {
      const raw = answer.trim();
      if (!raw) {
        resolve(defaultValue);
        return;
      }
      const val = Number(raw);
      if (Number.isNaN(val)) {
        console.log(chalk.red(` ✗ "${raw}" is not a number`));
        resolve(askNumber(question, defaultValue, options));
        return;
      }
      if (min !== undefined && val < min) {
        console.log(chalk.red(` ✗ Must be at least ${min}`));
        resolve(askNumber(question, defaultValue, options));
        return;
      }
      if (max !== undefined && val > max) {
        console.log(chalk.red(` ✗ Must be at most ${max}`));
        resolve(askNumber(question, defaultValue, options));
        return;
      }
      resolve(val);
    });
  });
}

export function askYesNo(question: string, defaultValue: boolean = false): Promise<boolean> {
  const suffix = defaultValue ? " [Y/n] " : " [y/N] ";
  return new Promise((resolve) => {
    rl.question(chalk.cyan(` ${question}${suffix}`), (answer) => {
      const raw = answer.trim().toLowerCase();
      if (!raw) {
        resolve(defaultValue);
        return;
      }
      resolve(raw === "y" || raw === "yes");
    });
  });
}

export function askChoice<T>(
  question: string,
  choices: { label: string; value: T; hint?: string }[],
  defaultIndex: number = 0
): Promise<T> {
  console.log(chalk.cyan(` ${question}`));
  choices.forEach((c, i) => {
    const marker = i === defaultIndex ? chalk.green(" ›") : "  ";
    const hint = c.hint ? chalk.gray(` (${c.hint})`) : "";
    console.log(` ${marker} ${i + 1}. ${c.label}${hint}`);
  });

  return new Promise((resolve) => {
    rl.question(chalk.cyan(` Pilih [1-${choices.length}] (default ${defaultIndex + 1}): `), (answer) => {
      const raw = answer.trim();
      if (!raw) {
        resolve(choices[defaultIndex].value);
        return;
      }
      const idx = parseInt(raw, 10) - 1;
      if (Number.isNaN(idx) || idx < 0 || idx >= choices.length) {
        console.log(chalk.red(` ✗ Invalid choice`));
        resolve(askChoice(question, choices, defaultIndex));
        return;
      }
      resolve(choices[idx].value);
    });
  });
}

export function closePrompts(): void {
  rl.close();
}