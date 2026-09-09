# 一机一码授权和 Nuitka 打包流程

## 1. 生成密钥

```powershell
.\.venv\Scripts\python.exe scripts\license_admin.py gen-key --private-key license_private.pem --public-key license_public.pem
```

私钥只放在你自己的电脑上，不能上传到 Gitee，也不能放进 exe。公钥可以用于打包。

## 2. 客户获取机器码

未授权机器启动 exe 后，会弹出“软件授权”窗口。让客户复制机器码发给你。

开发时如果还没配置授权，可以临时这样运行源码：

```powershell
$env:ZFN_DEV_SKIP_LICENSE='1'
.\.venv\Scripts\python.exe main.py
```

这个跳过开关只在源码运行时生效，Nuitka 打包后的 exe 不会理会它。

## 3. 签发授权

推荐直接打开授权管理器：

```powershell
.\dist_nuitka\授权管理器.exe
```

日常操作只需要粘贴客户机器码，填客户备注，然后点“签发并推送”。它会自动更新 `licenses.json` 并通过 SSH 推送到 Gitee。

也可以继续用命令行：

```powershell
.\.venv\Scripts\python.exe scripts\license_admin.py issue `
  --hwid "客户发来的机器码" `
  --private-key license_private.pem `
  --expires-at 2027-07-04 `
  --owner "客户备注" `
  --licenses licenses.json
```

`licenses.json` 会变成下面这种结构：

```json
{
  "version": 1,
  "licenses": [
    {
      "license_id": "...",
      "hwid_hash": "...",
      "expires_at": "2027-07-04",
      "features": ["full"],
      "issued_at": "2026-07-04",
      "signature": "..."
    }
  ]
}
```

把 `licenses.json` 上传到 Gitee。客户端只认 RSA 签名，所以别人即使改了 Gitee 文件，也无法伪造新授权。

## 4. 打包 exe

先拿到 Gitee 的 raw 文件地址，形式类似：

```text
https://gitee.com/你的用户名/你的仓库/raw/master/licenses.json
```

然后执行：

```powershell
.\.venv\Scripts\python.exe build_nuitka.py `
  --license-url "https://gitee.com/你的用户名/你的仓库/raw/master/licenses.json" `
  --public-key license_public.pem
```

生成结果在 `dist_nuitka\岭南师范学院教务管理助手.exe`。

## 5. 授权更新

客户付款或续期后，你只需要重新运行 `issue` 写入 `licenses.json`，再推到 Gitee。客户点“刷新授权”即可进入，不需要重新打包。

## 6. 打包保护级别

当前 exe 使用 Nuitka onefile 编译，并开启 release/hardening 参数：`--deployment`、`--lto=yes`、`--python-flag=no_asserts`、`--python-flag=no_docstrings`、无控制台、压缩 onefile、清理中间产物。

注意：任何本地软件都不存在绝对“无法逆向”。这个方案的重点是把私钥留在你手里，用 RSA 签名防伪造授权，并用 Nuitka 编译提高逆向成本。如果还要再往上加保护，需要额外使用 VMProtect、Themida、WinLicense 这类商业壳。
