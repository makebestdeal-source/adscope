/**
 * Icon generator for PWA
 * Usage: node scripts/generate-icons.js
 *
 * Generates PNG icons from SVG for PWA manifest.
 * Requires: npm install sharp (run once)
 */
const fs = require("fs");
const path = require("path");

const SVG_ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="64" fill="#0f172a"/>
  <rect x="24" y="24" width="464" height="464" rx="48" fill="none" stroke="#3b82f6" stroke-width="4" opacity="0.3"/>
  <text x="256" y="200" text-anchor="middle" font-family="Arial,sans-serif" font-size="180" font-weight="bold" fill="#3b82f6">A</text>
  <text x="256" y="340" text-anchor="middle" font-family="Arial,sans-serif" font-size="72" font-weight="600" fill="#94a3b8">Scope</text>
  <circle cx="380" cy="120" r="40" fill="#3b82f6" opacity="0.2"/>
  <circle cx="380" cy="120" r="20" fill="#3b82f6"/>
</svg>`;

const SVG_MASKABLE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#0f172a"/>
  <text x="256" y="220" text-anchor="middle" font-family="Arial,sans-serif" font-size="160" font-weight="bold" fill="#3b82f6">A</text>
  <text x="256" y="340" text-anchor="middle" font-family="Arial,sans-serif" font-size="64" font-weight="600" fill="#94a3b8">Scope</text>
</svg>`;

const iconsDir = path.join(__dirname, "..", "public", "icons");
fs.mkdirSync(iconsDir, { recursive: true });

async function generate() {
  let sharp;
  try {
    sharp = require("sharp");
  } catch {
    console.log("sharp not installed. Installing...");
    require("child_process").execSync("npm install sharp", {
      cwd: path.join(__dirname, ".."),
      stdio: "inherit",
    });
    sharp = require("sharp");
  }

  const sizes = [192, 512];

  for (const size of sizes) {
    await sharp(Buffer.from(SVG_ICON))
      .resize(size, size)
      .png()
      .toFile(path.join(iconsDir, `icon-${size}x${size}.png`));
    console.log(`Created icon-${size}x${size}.png`);

    await sharp(Buffer.from(SVG_MASKABLE))
      .resize(size, size)
      .png()
      .toFile(path.join(iconsDir, `icon-maskable-${size}x${size}.png`));
    console.log(`Created icon-maskable-${size}x${size}.png`);
  }

  // Favicon
  await sharp(Buffer.from(SVG_ICON))
    .resize(32, 32)
    .png()
    .toFile(path.join(iconsDir, "..", "favicon.ico"));
  console.log("Created favicon.ico");

  // Apple touch icon
  await sharp(Buffer.from(SVG_ICON))
    .resize(180, 180)
    .png()
    .toFile(path.join(iconsDir, "..", "apple-touch-icon.png"));
  console.log("Created apple-touch-icon.png");

  console.log("\nAll icons generated successfully!");
}

generate().catch(console.error);
