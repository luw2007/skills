# Domain: Linux Kernel Vulnerability Discovery

针对 Linux 内核源码的安全漏洞搜索。重点寻找**内存安全**和**权限边界**类漏洞。

## 前置条件

- 本地有完整内核源码 clone（设为 `$KERNEL_SRC`）
- 或通过 `--source-path` 指定

## enumerate

### 方法

根据目标漏洞模式，从攻击面出发枚举候选子系统。

**攻击面分类**（非特权用户可达）：

1. **User namespace 可达的网络子系统**
   ```bash
   grep -r "ns_capable.*CAP_NET" $KERNEL_SRC/net/ | cut -d: -f1 | sort -u
   ```

2. **Splice/零拷贝消费者**（文件页变成 skb frag 的入口）
   ```bash
   grep -rn "splice_write\|sendpage\|MSG_SPLICE_PAGES\|SPLICE_F_MOVE" $KERNEL_SRC/net/ $KERNEL_SRC/fs/
   ```

3. **In-place crypto/变换操作**（对 skb frag 就地修改）
   ```bash
   grep -rn "sg_set_page\|skb_page_frag\|crypto_.*decrypt\|crypto_.*encrypt" $KERNEL_SRC/net/ $KERNEL_SRC/crypto/
   ```

4. **独立接收路径**（绕过发送端保护的入口）
   ```bash
   # UDP encap — 外部构造的包直接进入协议处理
   grep -rn "encap_rcv\|udp_encap\|UDP_ENCAP" $KERNEL_SRC/net/
   # Tunnel rcv — VTI/GRE/IPIP 的独立接收入口
   grep -rn "tunnel.*rcv\|xfrm.*rcv\|vti.*input" $KERNEL_SRC/net/
   # 非对称协议 — input 函数不依赖 output 函数先执行
   grep -rn "\.input\s*=\|\.handler\s*=" $KERNEL_SRC/net/ | grep -v test
   ```

5. **Page-cache 写入点**
   ```bash
   grep -rn "set_page_dirty\|SetPageDirty\|mark_page_accessed" $KERNEL_SRC/mm/ $KERNEL_SRC/fs/
   ```

### 候选输出示例

```json
[
  {"name": "xfrm/esp splice path", "hypothesis": "ESP decrypt may write back to file-backed page via splice", "difficulty": 2, "method": "trace splice → xfrm_input data flow", "impact": 0.9, "probability": 0.3},
  {"name": "rxrpc/rxkad verify", "hypothesis": "rxkad_verify_packet does in-place decrypt on splice page", "difficulty": 2, "method": "read rxkad.c verify functions", "impact": 0.9, "probability": 0.2},
  {"name": "tls/ktls decrypt", "hypothesis": "kTLS decrypt path may modify file page", "difficulty": 2, "method": "trace tls_sw_recvmsg splice handling", "impact": 0.8, "probability": 0.2},
  {"name": "netfilter conntrack", "hypothesis": "conntrack helper modifies skb in-place", "difficulty": 1, "method": "grep conntrack helpers for skb write", "impact": 0.6, "probability": 0.1}
]
```

## probe

### 对每个候选路径的浅探测步骤

1. **定位目标函数** — 读取候选子系统的主文件（如 `net/xfrm/xfrm_input.c`）
2. **穷举所有 caller（必须）** — 不可从"最常见路径"推断输入特征
3. **对每个 caller 独立分析 page 来源** — 该 caller 路径是否能接收 file-backed page？
4. **判断写回** — 解密/变换操作是否 in-place？是否有 `skb_cow` / `pskb_copy` 保护？
5. **判断可达性** — 非特权用户（通过 user ns）能否触发此路径？

### ⚠️ 排除前强制检查清单（SOUNDNESS GATE）

**每次标记 "failed" 之前，必须逐项确认以下所有条件**：

```
□ CALLER 完备性: 列出目标函数的所有 caller（grep，非推断）
□ 逐路径分析: 对每个独立 caller，单独判断输入数据的页面来源
□ SPLICE 路径: 是否存在 splice/sendfile/vmsplice 路径到达目标函数？
□ 绕过前置保护: 攻击者是否可以在不经过"保护性"前置函数的情况下到达？
□ INPUT vs OUTPUT 独立性: 如果函数同时作为 input 和 output，两个方向是否有独立入口？
□ 外部输入: 是否存在网络接收路径（UDP encap、tunnel rcv 等）直接到达？
```

**如果任一项未确认或无法确认 → 状态必须为 "blocked"，不得标记 "failed"。**

### 判定标准

- **success**: file-backed page 可达 + in-place write 存在 + 无 copy 保护 + 非特权可触发
- **failed**: **所有** caller 路径都已验证不满足条件（排除检查清单全部✓）
- **blocked**: 存在未验证的 caller / 代码过于复杂 / 依赖未确认的前提

### 常见错误排除模式（必须避免）

| 错误模式 | 正确做法 |
|----------|----------|
| "output 会替换页面，所以 input 也是安全的" | output 和 input 是独立入口，分别分析 |
| "正常流量路径有保护，所以所有路径都有保护" | 穷举全部 caller，含 error path / fast path / encap path |
| "splice 到 socket 后页面就不是 file-backed 了" | 验证：splice 是零拷贝，skb frag 仍引用原始文件页 |
| "该子系统不处理外部输入" | 检查是否有 UDP encap / tunnel / loopback 接收路径 |
| "需要 CAP_X 权限" | 确认 user namespace 中是否已获得该 capability |

### 工具使用

```bash
# 【必须】穷举目标函数的所有调用者
grep -rn "函数名\|\.input\s*=\|\.handler\s*=" $KERNEL_SRC/net/ $KERNEL_SRC/include/

# 【必须】检查每个 caller 的数据来源
# 例：esp_input 有哪些入口？
grep -rn "xfrm_input\|xfrm4_rcv\|xfrm4_udp_encap_rcv\|xfrm4_tunnel_rcv" $KERNEL_SRC/net/ipv4/

# 检查 splice 是否传递 page（零拷贝 = 文件页直接变成 skb frag）
grep -rn "splice\|sendpage\|MSG_SPLICE_PAGES\|SPLICE_F_MOVE" $KERNEL_SRC/net/ipv4/

# 检查是否有 copy 保护
grep -n "skb_cow\|pskb_copy\|skb_copy\|copy_page" $KERNEL_SRC/net/xfrm/xfrm_input.c

# 检查 user-ns 可达性
grep -n "ns_capable\|capable" $KERNEL_SRC/net/xfrm/xfrm_user.c

# 检查 UDP encap 接收路径（常被忽视的独立入口）
grep -rn "udp_encap_rcv\|encap_rcv\|UDP_ENCAP" $KERNEL_SRC/net/ipv4/
```

## drill

### 确认可行后的深度分析

1. **完整调用链追踪** — 从 `splice(file → pipe → socket)` 到最终 decrypt 函数的每一跳
2. **写入内容可控性** — 攻击者能否控制写入的具体字节？（key、iv、seq 等）
3. **写入偏移可控性** — 能否选择文件的哪个偏移被修改？
4. **文件选择** — 能否指定目标文件（如 setuid binary、/etc/passwd）？
5. **PoC 可行性** — 是否需要 race condition？时间窗口多大？

### 输出子节点示例

```json
[
  {"name": "控制写入字节", "hypothesis": "seq_hi 字段可通过 xfrm SA 配置任意设置", "difficulty": 1, "method": "创建 SA 验证 seq_hi 写入"},
  {"name": "选择目标文件", "hypothesis": "splice 的 source fd 可以是任意只读打开的文件", "difficulty": 1, "method": "测试 splice(readonly_fd)"},
  {"name": "绕过 page 保护", "hypothesis": "UDP encap 路径不经过 skb_cow", "difficulty": 2, "method": "代码审计 udp_queue_rcv_one_skb 路径"}
]
```

## reflect

### 失败模式分析

常见排除原因及对策：

| 排除原因 | 新方向 |
|----------|--------|
| "有 skb_cow 保护" | 寻找跳过 cow 的特殊路径（如 fast path、error path、encap path） |
| "page 是 kernel alloc 的" | 寻找其他零拷贝 API（io_uring、sendfile、vmsplice） |
| "需要 CAP_NET_ADMIN" | 确认 user namespace 是否足够；检查 autoload 路径 |
| "只写 metadata 不写 data" | 扩展搜索到 checksum writeback、状态机更新 |
| "output 替换了页面" | **回查**: input 是否有独立入口不经过 output？ |
| "主路径有保护" | **回查**: error path / UDP encap / tunnel rcv 是否也有保护？ |

### ⚠️ reflect 阶段必须执行的回溯审计

在生成新方向之前，对所有 "failed" 节点执行回溯检查：

```
对每个 failed 节点:
  1. 其排除理由是否只验证了一条路径？
     → 如果是，重新标记为 "blocked"，要求穷举其余路径
  2. 是否存在 "因为 A 所以 B" 的推理链？
     → 验证 A→B 是否在所有场景下成立
  3. 排除理由中是否包含 "通常"、"一般"、"正常情况下" 等词？
     → 含义词标志着不完备分析，重新标记为 "blocked"
```

### 扩展搜索方向

当标准 splice + crypto 路径耗尽时：
- io_uring 的零拷贝路径
- DMA 相关的 page 共享
- 文件系统 direct IO 与 page cache 的交互
- BPF map 与 page cache 的交互
- UDP encapsulation 接收路径（独立于发送路径的入口）
- tunnel 解封装路径（VTI、GRE、IPIP 的 rcv 端）
- MSG_SPLICE_PAGES 在非标准协议中的使用
