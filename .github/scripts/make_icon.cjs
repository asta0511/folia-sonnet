// 把任意图片转成 1024x1024 白底 PNG，作为 @capacitor/assets 的图标源。
// sharp 是 @capacitor/assets 的依赖，安装依赖后即可直接使用，无需额外装 ImageMagick。
const path = require('node:path');
const { createRequire } = require('node:module');

const input = process.argv[2];
const output = process.argv[3];

if (!input || !output) {
  console.error('usage: node make_icon.cjs <input-image> <output.png>');
  process.exit(2);
}

function loadSharp() {
  const localRequire = createRequire(path.join(process.cwd(), 'package.json'));
  try {
    return localRequire('sharp');
  } catch {
    const assetsRequire = createRequire(path.join(process.cwd(), 'node_modules', '@capacitor', 'assets', 'package.json'));
    return assetsRequire('sharp');
  }
}

const sharp = loadSharp();

sharp(input)
  .flatten({ background: '#ffffff' })
  .resize(1024, 1024, { fit: 'cover', position: 'center' })
  .png({ compressionLevel: 9 })
  .toFile(output)
  .then((info) => {
    console.log(`icon source ready: ${output} ${info.width}x${info.height} (${info.size} bytes)`);
  })
  .catch((err) => {
    console.error('failed to build icon source:', err);
    process.exit(1);
  });
