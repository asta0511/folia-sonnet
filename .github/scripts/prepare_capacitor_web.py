#!/usr/bin/env python3
"""把 folia-major 的网页层改造成 Capacitor(Android) 构建目标。

CI 里在「用最新网页层覆盖工程」之后调用：
  python3 .github/scripts/prepare_capacitor_web.py /tmp/sonnet-package.json /tmp/web

做两件事：
1. 以 **folia-major 的 package.json** 为基准（网页层依赖），合并 Capacitor 相关依赖与构建脚本；
   基准必须用网页层的，否则依赖版本还是 sonnet 内嵌的旧版（v0.6.7），缺 pinyin-pro 等新依赖；
2. 生成 vite.config.capacitor.ts：base 改为相对路径、去掉 PWA 插件
   （WebView 里不需要 Service Worker，且它会把旧产物缓存住）。
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(".")

DEFAULT_FOLIA_API_BASE = "https://folia.789511.xyz/api"

# APK 里页面的 Origin 是 https://localhost，而上游把主题生成 / 歌词分词 / 歌词代理写成相对路径
# （/api/...）；不重写就会打到 WebView 自己的本地服务上（404）。runtime-config.js 在 index.html
# 里先于应用代码加载，正好用来装这个改写。上游只在这里放 aiProvider，我们顺手接管 fetch。
RUNTIME_CONFIG_TEMPLATE = """// 由 .github/scripts/prepare_capacitor_web.py 生成，勿手工编辑。
window.__FOLIA_RUNTIME_CONFIG__ = window.__FOLIA_RUNTIME_CONFIG__ || {};
(function () {
  var base = '__API_BASE__';
  if (!base) return;
  var original = window.fetch;
  window.fetch = function (input, init) {
    try {
      if (typeof input === 'string' && input.indexOf('/api/') === 0) {
        // '/api/xxx' -> '<base>/xxx'
        input = base + input.slice(4);
      } else if (input && typeof input.url === 'string') {
        var prefix = location.origin + '/api/';
        if (input.url.indexOf(prefix) === 0) {
          input = new Request(base + input.url.slice(prefix.length - 1), input);
        }
      }
    } catch (error) {
      /* 改写失败就用原请求，不在这里阻断 */
    }
    return original.call(this, input, init);
  };
})();
"""

CAPACITOR_SCRIPTS = {
    "build:capacitor": (
        "cross-env FOLIA_BUILD_TARGET=capacitor vite build --config vite.config.capacitor.ts"
    ),
    "cap:sync:android": "npm run build:capacitor && cap sync android",
    "cap:open:android": "cap open android",
}

# 打 APK 用不到桌面端运行时，装它们要多下 ~100MB 并跑 electron 的 postinstall。
DROP_DEV_DEPENDENCIES = ("electron", "electron-builder")

VITE_CONFIG_CAPACITOR = """// 由 .github/scripts/prepare_capacitor_web.py 生成，勿手工编辑。
// Capacitor(Android) 构建目标：复用上游 vite.config.ts，只改两处。
import baseConfigFactory from './vite.config';

// vite-plugin-pwa 会注册 Service Worker；WebView 内不需要，且它会缓存住旧产物。
const isPwaPlugin = (plugin: any): boolean =>
  typeof plugin?.name === 'string' && /^(vite-plugin-pwa|workbox)/.test(plugin.name);

export default async function capacitorConfig(env: any) {
  const config: any = await (baseConfigFactory as any)(env);
  const plugins = (Array.isArray(config.plugins) ? config.plugins : []).flat(Infinity) as any[];

  return {
    ...config,
    // Capacitor 以 https://localhost 提供本地文件，相对路径最稳。
    base: './',
    plugins: plugins.filter((plugin) => !isPwaPlugin(plugin)),
  };
}
"""


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: prepare_capacitor_web.py <sonnet-package.json> <web-layer-dir>", file=sys.stderr)
        return 2

    sonnet_pkg = json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8"))
    sonnet_all = {
        **sonnet_pkg.get("dependencies", {}),
        **sonnet_pkg.get("devDependencies", {}),
    }
    capacitor_deps = {k: v for k, v in sonnet_all.items() if "capacitor" in k.lower()}
    if not capacitor_deps:
        print("ERROR: 没有从 sonnet 的 package.json 里读到 Capacitor 依赖", file=sys.stderr)
        return 1

    web_pkg_path = pathlib.Path(argv[2]) / "package.json"
    pkg = json.loads(web_pkg_path.read_text(encoding="utf-8"))

    dev_deps = pkg.setdefault("devDependencies", {})
    dev_deps.update(capacitor_deps)
    for name in DROP_DEV_DEPENDENCIES:
        dev_deps.pop(name, None)

    pkg.setdefault("scripts", {}).update(CAPACITOR_SCRIPTS)

    (ROOT / "package.json").write_text(
        json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / "vite.config.capacitor.ts").write_text(VITE_CONFIG_CAPACITOR, encoding="utf-8")

    api_base = (os.environ.get("VITE_FOLIA_API_BASE") or DEFAULT_FOLIA_API_BASE).rstrip("/")
    runtime_config = ROOT / "public" / "runtime-config.js"
    runtime_config.parent.mkdir(parents=True, exist_ok=True)
    runtime_config.write_text(
        RUNTIME_CONFIG_TEMPLATE.replace("__API_BASE__", api_base), encoding="utf-8"
    )

    # @capacitor/cli 用 require('typescript') 转译 .ts 配置，而网页层的依赖是 TypeScript 7，
    # 其 ModuleKind 已不可用（TypeError: reading 'CommonJS'）。有 JSON 版就删掉 .ts，让 CLI 走 JSON。
    ts_config = ROOT / "capacitor.config.ts"
    if ts_config.exists() and (ROOT / "capacitor.config.json").exists():
        ts_config.unlink()
        print("capacitor config  : 删除 capacitor.config.ts（改用 .json）")

    print(f"web layer version : {pkg.get('version')}")
    print(f"capacitor deps    : {', '.join(sorted(capacitor_deps))}")
    print(f"dropped devDeps   : {', '.join(DROP_DEV_DEPENDENCIES)}")
    print(f"api base (shim)   : {api_base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
