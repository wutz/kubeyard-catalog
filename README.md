# kubeyard-catalog

Kubeyard 默认组件目录。以 OCI artifact 发布到 `oci://ghcr.io/wutz/kubeyard-catalog`，由 Flux `OCIRepository` 拉取，经 cosign 校验后安装。

- 版本：`vYYYY.MM.N`（不可变）；`stable` 指向当前推荐版本
- 签名：cosign 密钥对，公钥见 [cosign.pub](cosign.pub)
- 目录索引：[catalog.yaml](catalog.yaml)，host 推荐组合：[profiles/host.yaml](profiles/host.yaml)

## 目录结构

```
catalog.yaml          索引（GUI 首先读取）
cosign.pub            签名公钥（同时作为集群内 Secret 的数据源）
profiles/             推荐组合
addons/<name>/
  addon.yaml          元数据：分类、适用范围、版本、依赖、命名空间
  schema.json         参数 JSON Schema，GUI 据此渲染表单
  manifests/          Flux 清单（kustomization 根）
scripts/validate.py   结构与清单校验
```

## 安装模型

安装一个条目 = 在 `kubeyard-system` 中创建一个 Flux `Kustomization`，指向 `addons/<name>/manifests`：

- `postBuild.substitute.addon_namespace`：目标命名空间（来自 `addon.yaml` 的 `namespace`）
- `metallb` 额外使用 `metallb_addresses`：LoadBalancer 地址池
- 参数：GUI 写入 `ConfigMap addon-<name>-params`（键 `values.yaml`），HelmRelease 以 `valuesFrom` 可选引用
- 依赖：`addon.yaml` 的 `dependsOn` 映射为 Kustomization 的 `dependsOn`

## 与 k8s-in-action 的差异

| 条目 | 差异 |
|---|---|
| 所有 chart | 使用上游源（`registry.k8s.io`、`quay.io`、`gcr.io`、`ghcr.io`、NGC、GitHub Pages），不含 `mir.blsc.cn` 镜像；镜像覆盖在集群设置中配置 |
| spegel | 镜像列表不含内网镜像站 |
| istio | 去掉 `ENABLE_GATEWAY_API_INFERENCE_EXTENSION`（需要额外 CRD）；ambient 与 Ingress 网关未包含 |
| gpu-operator | 默认不装驱动（假设节点镜像已带驱动）；未包含 DCGM 的 kustomize 补丁 |
| nfd | 未包含按机器名打 instance-type 的 NodeFeatureRule（站点特定） |
| metallb | 地址池默认为文档示例段，安装时必须通过 `metallb_addresses` 覆盖 |
| cert-manager | 未包含 ClusterIssuer（站点特定） |

## 发布

推送 `v*` 标签触发 [publish 工作流](.github/workflows/publish.yml)：校验 → `flux push artifact` → 打 `stable` → cosign 签名 → 验签。

私钥与口令只存在于仓库 Secret `COSIGN_PRIVATE_KEY` / `COSIGN_PASSWORD`。轮换密钥时需同步更新所有集群中的 `catalog-default-cosign-pub` Secret。

## 本地校验

```bash
python3 scripts/validate.py
```

需要 `kustomize`、`pyyaml`、`jsonschema`。
