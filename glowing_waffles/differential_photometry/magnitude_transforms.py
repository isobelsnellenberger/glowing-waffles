from __future__ import print_function, division

import numpy as np

from astropy.modeling import models, fitting
from astropy.stats import sigma_clip

__all__ = [
    'filter_transform',
    'calculate_transform_coefficients',
]


def filter_transform(mag_data, output_filter,
                     g=None, r=None, i=None,
                     transform=None):
    '''
    Transform SDSS magnitudes to BVRI.

    Parameters
    ----------

    mag_data : astropy.table.Table
        Table containing ``g``, ``r`` and ``i`` magnitudes (or at least)
        those required to transform to the desired output filter.
    output_filter : 'B', 'V', 'R' or 'I'
        Filter for which magnitude should be calculated. Note that
        *case matters* here.
    g, r, i : str
        Name of column in table for that magnitude.
    transform : 'jester' or 'ivezic'
        Transform equations to use.
    Description: This function impliments the transforms in
        'A Comparison of SDSS Standard

    Returns
    -------

    astropy.table.Column
        Output magnitudes as table column
    '''
    supported_transforms = ['jester', 'ivezic']
    if transform not in supported_transforms:
        raise ValueError('Transform {} is not known. Must be one of '
                         '{}'.format(transform, supported_transforms))
    transform_ivezic = {
        'B': [0.2628, -0.7952, 1.0544, 0.0268],
        'V': [0.0688, -0.2056, -0.3838, -0.0534],
        'R': [-0.0107, 0.0050, -0.2689, -0.1540],
        'I': [-0.0307, 0.1163, -0.3341, -0.3584]
    }
    base_mag_ivezic = {
        'B': g,
        'V': g,
        'R': r,
        'I': i
    }
    # For jester, using the transform for "all stars with Rc-Ic < 1.15"
    # from
    # http://www.sdss3.org/dr8/algorithms/sdssUBVRITransform.php#Jester2005
    jester_transforms = {
        'B': [1.39, -0.39, 0, 0.21],
        'V': [0.41, 0.59, 0, -0.01],
        'R': [0.41, -0.5, 1.09, -0.23],
        'I': [0.41, -1.5, 2.09, -0.44]
    }

    if output_filter not in base_mag_ivezic.keys():
        raise ValueError('the desired filter must be a string R B V or I')

    if transform == 'ivezic':
        if output_filter == 'R' or output_filter == 'I':
            # This will throw a KeyError if the column is missing
            c = mag_data[r] - mag_data[i]

        if output_filter == 'B' or output_filter == 'V':
            # This will throw a KeyError if the column is missing
            c = mag_data[g] - mag_data[r]

        transform_poly = np.poly1d(transform_ivezic[output_filter])
        out_mag = transform_poly(c) + \
            mag_data[base_mag_ivezic[output_filter]]
        # poly1d  ignores masks. Add masks back in here if necessary.
        try:
            input_mask = c.mask
        except AttributeError:
            pass
        else:
            out_mag = np.ma.array(out_mag, mask=input_mask)
    elif transform == 'jester':
        coeff = jester_transforms[output_filter]
        out_mag = (coeff[0] * mag_data[g] + coeff[1] * mag_data[r] +
                   coeff[2] * mag_data[i] + coeff[3])

    out_mag.name = '{}_mag'.format(output_filter)
    out_mag.description = ('{}-band magnitude transformed '
                           'from gri'.format(output_filter))
    return out_mag


def calculate_transform_coefficients(input_mag, catalog_mag, color,
                                     input_mag_error=None,
                                     catalog_mag_error=None,
                                     order=1):
    """
    Calculate linear transform coefficients from input magnitudes to catalog
    magnitudes.

    Parameters
    ----------

    input_mag : numpy array or astropy Table column
        Input magnitudes; for example, instrumental magnitudes.
    catalog_mag : numpy array or astropy Table column
        Catalog (or reference) magnitudes; the magnitudes to which the
        input_mag will eventually be transformed.
    color : numpy array or astropy Table column
        Colors to use in determining transform coefficients.
    input_mag_error : numpy array or astropy Table column, optional
        Error in input magnitudes. Default is zero.
    catalog_mag_error : numpy array or astropy Table column, optional
        Error in catalog magnitudes. Default is zero.
    order : int, optional
        Order of the polynomial fit to use in correcting for color.

    Returns
    -------

    zero_point, slope : float
        Zero point and linear color term in transform equation (see notes
        below).

    Notes
    -----

    This function has some pretty serious limitations right now:

    + Errors in the independent variable are ignored.
    + Outliers are rejected using a modified loss function (Huber loss) that
      cannot be modified.
    + No errors are estimated in the calculated transformation coefficients.

    And there is all the stuff that is not listed here...
    """

    if input_mag_error is None:
        input_mag_error = np.zeros_like(input_mag)
    if catalog_mag_error is None:
        catalog_mag_error = np.zeros_like(catalog_mag)

    # Independent variable is the color, dependent variable is the
    # difference between the measured (input) magnitude and the catalog
    # magnitude.

    mag_diff = catalog_mag - input_mag

    # The error is the errors of those combined in quadrature.
    combined_error = np.sqrt(input_mag_error**2 + catalog_mag_error**2)

    # If both errors are zero then the error is omitted.
    if (combined_error == 0).all():
        dy = None
    else:
        dy = combined_error

    g_init = models.Polynomial1D(order)
    fit = fitting.LinearLSQFitter()
    or_fit = fitting.FittingWithOutlierRemoval(fit, sigma_clip,
                                               niter=3, sigma=2.0)
    # get fitted model and filtered data
    filtered_data, or_fitted_model = or_fit(g_init, color, mag_diff)

    return (filtered_data, or_fitted_model)
