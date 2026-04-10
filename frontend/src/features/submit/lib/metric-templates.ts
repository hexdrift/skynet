export const METRIC_TEMPLATE_MIPRO = `def metric(example: dspy.Example, prediction: dspy.Prediction, trace: bool = None) -> float:
    # Return a numeric score (float/int/bool)

    pass
`;

export const METRIC_TEMPLATE_GEPA = `def metric(gold: dspy.Example, pred: dspy.Prediction, trace: bool = None, pred_name: str = None, pred_trace: list = None) -> dspy.Prediction:
    score = 0.0
    feedback = ""

    # Calculate score and feedback

    return dspy.Prediction(score=score, feedback=feedback)
`;

export const isMetricTemplate = (code: string): boolean =>
  code === METRIC_TEMPLATE_MIPRO || code === METRIC_TEMPLATE_GEPA;
