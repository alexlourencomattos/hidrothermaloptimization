param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms.DataVisualization
Add-Type -AssemblyName System.Drawing
$invariant = [System.Globalization.CultureInfo]::InvariantCulture
$chartNamespace = 'System.Windows.Forms.DataVisualization.Charting'

function Number([string]$value) { return [double]::Parse($value, $invariant) }

function New-Chart([string]$title, [string]$subtitle) {
    $chart = New-Object "$chartNamespace.Chart"
    $chart.Width = 1600
    $chart.Height = 1000
    $chart.BackColor = [System.Drawing.Color]::White
    $chart.AntiAliasing = 'All'
    $chart.TextAntiAliasingQuality = 'High'
    $heading = $chart.Titles.Add($title)
    $heading.Font = New-Object System.Drawing.Font('Segoe UI', 27, [System.Drawing.FontStyle]::Bold)
    $heading.ForeColor = [System.Drawing.ColorTranslator]::FromHtml('#17324d')
    $subheading = $chart.Titles.Add($subtitle)
    $subheading.Font = New-Object System.Drawing.Font('Segoe UI', 14)
    $footer = $chart.Titles.Add('Modelo didático | Python puro | Dados normalizados | Tolerância: 1e-6')
    $footer.Docking = 'Bottom'
    $footer.Font = New-Object System.Drawing.Font('Segoe UI', 12)
    $footer.ForeColor = [System.Drawing.Color]::DimGray
    $legend = New-Object "$chartNamespace.Legend"
    $legend.Name = 'legend'
    $legend.Docking = 'Bottom'
    $legend.Font = New-Object System.Drawing.Font('Segoe UI', 14)
    $chart.Legends.Add($legend)
    return ,$chart
}

function Add-Area($chart, [string]$name, [string]$xTitle, [string]$yTitle) {
    $area = New-Object "$chartNamespace.ChartArea"
    $area.Name = $name
    $area.BackColor = [System.Drawing.Color]::White
    foreach ($axis in @($area.AxisX, $area.AxisY)) {
        $axis.LabelStyle.Font = New-Object System.Drawing.Font('Segoe UI', 12)
        $axis.TitleFont = New-Object System.Drawing.Font('Segoe UI', 15)
        $axis.MajorGrid.LineColor = [System.Drawing.ColorTranslator]::FromHtml('#e5ebf0')
        $axis.LineColor = [System.Drawing.ColorTranslator]::FromHtml('#9aaaba')
    }
    $area.AxisX.Title = $xTitle
    $area.AxisY.Title = $yTitle
    $area.AxisX.MajorGrid.Enabled = $false
    $area.AxisX.Interval = 1
    $chart.ChartAreas.Add($area)
    return ,$area
}

function Add-Series($chart, [string]$name, [string]$type, [string]$color, [string]$area) {
    $series = New-Object "$chartNamespace.Series"
    $series.Name = $name
    $series.ChartArea = $area
    $series.ChartType = $type
    $series.Color = [System.Drawing.ColorTranslator]::FromHtml($color)
    $series.BorderWidth = 4
    if ($type -eq 'Line') { $series.MarkerStyle = 'Circle'; $series.MarkerSize = 8 }
    $chart.Series.Add($series)
    return ,$series
}

function Save-Chart($chart, [string]$name) {
    $chart.SaveImage((Join-Path $OutputDirectory $name), 'Png')
    $chart.Dispose()
}

$data = Join-Path $OutputDirectory 'data'
$dispatch = Import-Csv -LiteralPath (Join-Path $data 'dispatch.csv')
$chart = New-Chart 'Usar água agora ou guardar para depois?' 'Despacho otimizado no cenário base | Solução por pontos interiores'
$area = Add-Area $chart 'dispatch' 'Período' 'Energia por período (u.n.)'
$area.AxisY.Minimum = 0
$area.AxisY.Maximum = 10
$area.AxisX.Minimum = 0.5
$area.AxisX.Maximum = 6.5
for ($period = 1; $period -le 6; $period++) {
    [void]$area.AxisX.CustomLabels.Add(($period - 0.5), ($period + 0.5), $period.ToString())
}
foreach ($spec in @(@('T1','#e8ac42'), @('T2','#d56847'), @('Hidrelétrica','#2688b8'))) {
    $series = Add-Series $chart $spec[0] 'StackedColumn' $spec[1] 'dispatch'
    foreach ($row in $dispatch) {
        $value = if ($spec[0] -eq 'Hidrelétrica') { Number $row.hydro } else { Number $row.($spec[0]) }
        [void]$series.Points.AddXY((Number $row.period), $value)
    }
}
$series = Add-Series $chart 'Demanda' 'Line' '#17324d' 'dispatch'
$series.BorderDashStyle = 'Dash'
foreach ($row in $dispatch) { [void]$series.Points.AddXY((Number $row.period), (Number $row.demand)) }
Save-Chart $chart '01_dispatch.png'

$storage = Import-Csv -LiteralPath (Join-Path $data 'storage.csv')
$chart = New-Chart 'O reservatório conecta as decisões no tempo' 'Armazenamento ao fim de cada período | Período 0 = volume inicial'
$area = Add-Area $chart 'storage' 'Período' 'Água armazenada (u.n.)'
$area.AxisY.Minimum = 0
$area.AxisY.Maximum = 14
$area.AxisY.Interval = 2
$area.AxisX.Minimum = 0
$area.AxisX.Maximum = 6
foreach ($spec in @(@('base','Base | reserva final ≥ 5','#2688b8'), @('dry','Seco | metade da afluência','#d56847'), @('reserve','Reserva final ≥ 8','#21856b'))) {
    $series = Add-Series $chart $spec[1] 'Line' $spec[2] 'storage'
    foreach ($row in ($storage | Where-Object scenario -eq $spec[0])) {
        [void]$series.Points.AddXY((Number $row.period), (Number $row.storage))
    }
}
$capacity = Add-Series $chart 'Capacidade = 12' 'Line' '#8995a1' 'storage'
$capacity.BorderDashStyle = 'Dash'
$capacity.MarkerStyle = 'None'
[void]$capacity.Points.AddXY(0, 12)
[void]$capacity.Points.AddXY(6, 12)
Save-Chart $chart '02_storage.png'

$history = Import-Csv -LiteralPath (Join-Path $data 'convergence.csv')
$chart = New-Chart 'Dois caminhos para resolver o mesmo problema' 'Resíduos em escala logarítmica | As definições diferem entre os métodos (ver ESTUDO.md)'
$chart.Legends[0].Enabled = $false
foreach ($spec in @(@('interior_point','Pontos interiores'), @('admm','ADMM'))) {
    $name = $spec[0]
    $area = Add-Area $chart $name ('Iteração | ' + $spec[1]) 'Norma infinita / mu'
    $area.AxisY.IsLogarithmic = $true
    $area.AxisY.Minimum = 1e-16
    $area.AxisY.Maximum = 100
    $area.AxisY.LabelStyle.Format = '0E+0'
    $area.AxisX.Interval = if ($name -eq 'admm') { 20 } else { 2 }
    $area.AxisX.Minimum = 0
    $area.AxisX.Maximum = if ($name -eq 'admm') { 120 } else { 12 }
    $area.Position.X = if ($name -eq 'interior_point') { 2 } else { 51 }
    $area.Position.Y = 21
    $area.Position.Width = 47
    $area.Position.Height = 64
    $rows = @($history | Where-Object algorithm -eq $name)
    foreach ($metric in @(@('primal','#2688b8'), @('dual','#d56847'), @('complementarity','#21856b'))) {
        if ($name -eq 'admm' -and $metric[0] -eq 'complementarity') { continue }
        $series = Add-Series $chart ($name + '_' + $metric[0]) 'Line' $metric[1] $name
        $series.MarkerStyle = 'None'
        foreach ($row in $rows) {
            [void]$series.Points.AddXY((Number $row.iteration), [math]::Max(1e-16, (Number $row.($metric[0]))))
        }
    }
    $line = Add-Series $chart ($name + '_tolerance') 'Line' '#8995a1' $name
    $line.BorderDashStyle = 'Dash'
    $line.MarkerStyle = 'None'
    [void]$line.Points.AddXY(0, 1e-6)
    [void]$line.Points.AddXY((Number $rows[-1].iteration), 1e-6)
}
$note = $chart.Titles.Add('Azul: primal    Laranja: dual    Verde: complementaridade média (PI)    Tracejado: tolerância')
$note.Docking = 'Bottom'
$note.Font = New-Object System.Drawing.Font('Segoe UI', 13)
Save-Chart $chart '03_convergence.png'

$costs = Import-Csv -LiteralPath (Join-Path $data 'costs.csv')
$chart = New-Chart 'Menos água ou maior reserva: qual o custo?' 'Custo térmico total otimizado | Demanda idêntica nos três cenários'
$area = Add-Area $chart 'cost' 'Cenário' 'Custo total (u.m. do estudo)'
$area.AxisY.Minimum = 0
$area.AxisY.Maximum = 115
$chart.Legends[0].Enabled = $false
$series = Add-Series $chart 'Custo' 'Column' '#2688b8' 'cost'
$series.IsValueShownAsLabel = $true
$series.LabelFormat = '0.00'
$series.Font = New-Object System.Drawing.Font('Segoe UI', 20, [System.Drawing.FontStyle]::Bold)
$labels = @('Base', 'Seco', 'Maior reserva final')
$colors = @('#2688b8','#d56847','#21856b')
for ($i = 0; $i -lt $costs.Count; $i++) {
    $index = $series.Points.AddXY($labels[$i], (Number $costs[$i].objective))
    $series.Points[$index].Color = [System.Drawing.ColorTranslator]::FromHtml($colors[$i])
}
Save-Chart $chart '04_costs.png'
