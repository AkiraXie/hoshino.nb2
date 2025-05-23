/*
 * @Author: KBD
 * @Date: 2022-12-26 13:45:30
 * @LastEditors: KBD
 * @LastEditTime: 2023-01-13 01:35:34
 * @Description: 用于初始化手机动态页面的样式以及图片大小
 */
async function getMobileStyle(useImageBig = false) {
    // 删除 dom 的对象, 可以自行添加 ( className 需要增加 '.' 为前缀, id 需要增加 '#' 为前缀)
    const deleteDoms = {
        // 关注 dom
        followDoms: [".dyn-header__following", ".easy-follow-btn", ".dyn-orig-author__right"],
        // 分享 dom
        shareDoms: [".dyn-share"],
        // 打开程序 dom
        openAppBtnDoms: [".dynamic-float-btn", ".float-openapp"],
        // 导航 dom
        navDoms: [".m-navbar", ".opus-nav"],
        // 获取更多 dom
        readMoreDoms: [".opus-read-more"],
        // 全屏弹出 Dom
        openAppDialogDoms: [".openapp-dialog"],
        // 评论区 dom
        commentsDoms: [".v-switcher"],
        // 打开商品 dom
        openGoodsDoms: [".bm-link-card-goods__one__action", ".dyn-goods__one__action"],
        // 打开app dom
        openAppDoms: ["m-open-app.m-open-app.opus-float-btn"],
    }

    // 遍历对象的值, 并将多数组扁平化, 再遍历进行删除操作
    Object.values(deleteDoms).flat(1).forEach(domTag => {
        const deleteDom = document.querySelector(domTag);
        deleteDom && deleteDom.remove();
    })

    // 新版动态需要移除对应 class 达到跳过点击事件, 解除隐藏的目的 
    const contentDom = document.querySelector(".opus-module-content");
    contentDom && contentDom.classList.remove("limit");

    // 设置 mopus 的 paddingTop 为 0
    const mOpusDom = document.querySelector(".m-opus");
    if (mOpusDom) {
        mOpusDom.style.paddingTop = "0";
        mOpusDom.style.minHeight = "0";
    }

    // 删除老版动态 .dyn-card 上的字体设置
    const dynCardDom = document.querySelector(".dyn-card");
    if (dynCardDom) {
        dynCardDom.style.fontFamily = "unset";
    }

    // 获取图片容器的所有 dom 数组
    const imageItemDoms = Array.from(document.querySelectorAll(".bm-pics-block__item"));

    // 获取图片长宽比例
    const getImageRatio = (url) => {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.src = url;
            img.onload = () => {
                resolve(img.height / img.width);
            }
            img.onerror = () => {
                reject();
            }
        })
    };

    // 图片长宽比例的数组
    const ratioList = [];

    // TODO: 算法待优化
    // 异步遍历图片 dom
    await Promise.all(imageItemDoms.map(async (item) => {
        // 获取原app中图片的src
        const imgSrc = item.firstChild.src;
        // 判断是否有 @ 符
        const imgSrcAtIndex = imgSrc.indexOf("@");
        // 将所有图片转换为 .webp 格式节省加载速度, 并返回给原来的 image 标签
        item.firstChild.src = imgSrcAtIndex !== -1 ? imgSrc.slice(0, imgSrcAtIndex + 1) + ".webp" : imgSrc;
        // 获取图片的宽高比
        ratioList.push(await getImageRatio(item.firstChild.src));
    })).then(() => {
        // 判断 ratioList 中超过 1 的个数为 3 的倍数 且 ratioList 的长度大于 3
        const isAllOneLength = ratioList.filter(item => item >= 0.9 && item <= 1.1).length;
        const isAllOne = ratioList.length === 9 ? isAllOneLength > ratioList.length / 2 : isAllOneLength > 0 && isAllOneLength % 3 === 0 && ratioList.length > 3;
        // 说明可能为组装的拼图, 如果不是则放大为大图
        if (!isAllOne && useImageBig) {
            // 找到图标容器dom
            const containerDom = document.querySelector(".bm-pics-block__container");
            if (containerDom) {
                // 先把默认 padding-left 置为0
                containerDom.style.paddingLeft = "0";
                // 先把默认 padding-right 置为0
                containerDom.style.paddingRight = "0";
                // 设置 flex 模式下以列形式排列
                containerDom.style.flexDirection = "column";
                // 设置 flex 模式下每个容器间隔15px
                containerDom.style.gap = "15px";
                // flex - 垂直居中
                containerDom.style.justifyContent = "center";
                // flex - 水平居中
                containerDom.style.alignItems = "center";
            }

            // 新版动态需要给 bm-pics-block 的父级元素设置 flex 以及 column
            const newContainerDom = document.querySelector(".bm-pics-block")?.parentElement;
            if (newContainerDom) {
                // 设置为 flex
                newContainerDom.style.display = "flex";
                // 设置为竖向排列
                newContainerDom.style.flexDirection = "column";
                // flex - 垂直居中
                newContainerDom.style.justifyContent = "center";
                // flex - 水平居中
                newContainerDom.style.alignItems = "center";
            }

            imageItemDoms.forEach(item => {
                // 获取屏幕比例的 90% 宽度
                const clientWidth = window.innerWidth * 0.9;
                // 先把默认 margin 置为 0
                item.style.margin = "0";
                // 宽度默认撑满屏幕宽度 90%;
                item.style.width = `${clientWidth}px`;
                // 设置自动高度
                item.style.height = "auto";
            })
        } else {
            imageItemDoms.forEach(async (item) => {
                // 获取当前图片标签的 src
                const imgSrc = item.firstChild.src;
                // 获取 @ 符的索引
                const imgSrcAtIndex = imgSrc.indexOf("@");
                // 获取图片比例
                const ratio = await getImageRatio(item.firstChild.src);
                // 如果比例大于 3 即为长图, 则获取 header 图
                item.firstChild.src = ratio > 3 ? imgSrc.slice(0, imgSrcAtIndex + 1) + "260w_260h_!header.webp" : imgSrc.slice(0, imgSrcAtIndex + 1) + "260w_260h_1e_1c.webp";
            });
        }
    })
}


async function imageComplete() {
    // 异步渲染已经加载的图片地址, 如果已经缓存则会立即返回 true
    const loadImageAsync = (url) => {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.src = url;

            image.onload = () => {
                resolve(image.complete) // 理应为 true
            }

            image.onerror = () => {
                reject(false);
            }
        })
    }

    // 获取图片容器的所有 dom
    const imageItemDoms = document.querySelectorAll(".bm-pics-block__item");

    // 异步遍历图片并等待
    const imageItemStatusArray = await Promise.all(Array.from(imageItemDoms).map((item) => {
        return loadImageAsync(item.firstChild.src);
    }))

    // 通过遍历图片加载状态, 如果有一个图片加载失败, 均为 false
    return imageItemStatusArray.reduce((p, c) => {
        return p && c;
    }, true)
}
