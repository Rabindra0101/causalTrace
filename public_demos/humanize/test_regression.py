from subject import metric

def test_metric_preserves_significant_figures():
    assert metric(9.999e30, 'W') == '10.0 QW'
