# AV1 Open Source Codec Comparison

AOMedia Video 1 (AV1) is an open, royalty-free video coding format designed for video transmissions over the Internet. AV1 provides a set of state-of-the-art video compression tools that can compress the high quality video signals with high efficiency, without requiring licensing fees. libaom is the official software implementation of the AV1 coding standard. Besides libaom, there are two other popular AV1 compliant open source libraries, the Scalable Video Technology for AV1 (SVT-AV1) and Rust AV1 encoder (RAV1e). These codecs have their own features, for example, multi-thread encoding, faster encoding speed... The goal of this project is to, under certain use cases configurations, compare the coding tools in SVT-AV1 and RAV1e to libaom with regard to different coding quality metrics and speed, to provide insight into improvements which could be made to libaom or to proprietary AV1 encoders.

This repo contains the code that was used for this project. It mainly comprises of the perfomrance metric tool for evaluating the quality and speed of the encoders and git diffs for the experiments/code changes that were worked on during the project.

The experiment git diffs can be found in the [experiments branch](https://github.com/googleinterns/av1-codec-comparison/tree/experiments)

The folder `rtc-video-quality` is a [fork](https://github.com/google/rtc-video-quality) that was tweaked to make use of the AV1 encoders and use a template html to generate the graphs. You can learn more about it by reading the [readme](rtc-video-quality)
