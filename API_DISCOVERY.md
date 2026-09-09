# 教务系统接口发现记录

## 访问前提

- 校外访问需要先通过学校 WebVPN 完成统一身份认证。
- 教务系统菜单已确认可通过 VPN 正常打开；接口使用浏览器登录后的会话进行验证。
- 不要将账号、密码、验证码或浏览器 Cookie 写入配置文件、代码或日志。

当前校外测试使用的 `base_url` 为：

```text
https://csvpn.lingnan.edu.cn/http/77726476706e69737468656265737421fae00f902e3e6f5e7f06c7a99c406d36a1/
```

它已经设为账号添加窗口的默认地址。该地址本身可访问，但独立的 `requests.Session` 尚未完成 WebVPN 认证时会被重定向到 `/login`；因此不能仅靠替换 `base_url` 获得已登录会话。

## 已确认的功能入口

以下路径以教务系统根地址为基准，并需要携带已认证会话：

| 功能 | 菜单代码 | 入口路径 |
| --- | --- | --- |
| 个人课表 | `N2151` | `kbcx/xskbcx_cxXskbcxIndex.html` |
| 课表数据 | `N2151` | `kbcx/xskbcx_cxXsKb.html?gnmkdm=N2151` |
| 学生成绩 | `N305005` | `cjcx/cjcx_cxDgXscj.html?doType=query&gnmkdm=N305005` |
| 自主选课入口 | `N253512` | `xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default` |
| 待选课程列表 | `N253512` | `xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512` |
| 教学班列表 | `N253512` | `xsxk/zzxkyzbjk_cxJxbWithKchZzxkYzb.html?gnmkdm=N253512` |
| 已选课程 | `N253512` | `xsxk/zzxkyzb_cxZzxkYzbChoosedDisplay.html?gnmkdm=N253512` |
| 个人信息 | `N100801` | `xsxxxggl/xsxxwh_cxCkDgxsxx.html?gnmkdm=N100801` |

## 与当前代码的对应关系

这些接口已由 [`api/zfn_api.py`](api/zfn_api.py) 封装。功能测试应优先复用 `Client` 与 `SessionManager`，并将根地址通过 `base_url` 参数注入；不要硬编码 WebVPN 的动态转发 URL。

选课请求依赖入口页中的动态隐藏字段（例如 `xkkz_id`、`kklxdm`、`xkxnm`、`xkxqm`）。测试时必须先请求选课入口页，再使用本次会话解析出的字段构造后续请求。

## 推荐的只读测试顺序

1. 确认会话：`xtgl/index_initMenu.html`
2. 查询课表：`kbcx/xskbcx_cxXsKb.html?gnmkdm=N2151`
3. 查询成绩：`cjcx/cjcx_cxDgXscj.html?doType=query&gnmkdm=N305005`
4. 如需测试选课解析，仅请求自主选课入口和课程列表；不要在自动化测试中调用选课或退选接口。
